#!/usr/bin/env python

#    This script picks a random album from the MPD playlist.
#    Copyright (C) 2009  Kyle MacLeod  kyle.macleod is at gmail
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Description
-----------
This script picks a random album from the MPD playlist.  Called with no
args it will choose the first song from a random album on the current playlist
and start playing from that point. Obviously, this only works if the playlist
is arranged as a list of albums. It's meant to provide a rudimentary album-level
shuffle function for MPD.

In daemon mode the script will monitor MPD and select a new album
in the playlist after the last song on an album has ended (see -d option).

Options:

    -h|--help
    -d|--daemon  : Daemon mode. Monitors MPD for track changes. At end of album selects
                   a new random album from the playlist
    -D|--debug   : Print debug messages to stdout
    -p|--passive : Testing only. Does not make any changes to the MPD playlist.

Dependencies:

* python2-mpd  : still using the python2 mpd library (for now)

Limitations:

* The album switching is currently triggered when the last song on an album is
  reached.  If the user changes the current song selection during the last song
  on an album then this script will kick in, randomly selecting a new album.
  Unfortunately I don't see how to avoid this unless we were to time how long the
  last song has been playing for, and compare it to the song length given by MPD.


Usage Notes:
------------

### Album Queue

A file specified by environment variable MPD_RANDOM_ALBUM_QUEUE_FILE [default=/tmp/mpd.albumq]
can be used to enqueue individual albums to be played in order.

Put album titles to be enqueued in $MPD_RANDOM_ALBUM_QUEUE_FILE, one line per album.
Album names are consumed as a queue, until the file is empty, after which the selector will
revert back to random.

By default, the given album string matches the first album against any
substring in the playlist album names (case-sensitive). For an exact match,
prefix the album name with a '!'.

An example /tmp/mpd.albumq:

    Abbey Road
    !Movement (Remastered)


### Temporarily Suspend (mpd.norandom file)

When the file specified by environment variable MPD_RANDOM_SUSPEND_FILE [default=/tmp/mpd.norandom]
is created, then this script ignores album changes.

You can use this to temporarily override album selection when the script is
running in daemon mode. e.g.:

    touch /tmp/mpd.norandom


Examples
--------

Select a new album to play from the current playlist:

    ./mpd-random-playlist-album.py

Start a daemon, logging output to /tmp/mpd-random-playlist-album.log

    (./mpd-random-playlist-album.py -d > /tmp/mpd-random-playlist-album.log 2>&1 ) &
"""

import getopt
import logging
import mpd
import os
import os.path
import random
import sys
import tempfile
import time
import traceback

# If this file exists then no random album is chosen. Used to easily disable the daemon
# e.g. touch /tmp/mpd.norandom && sleep 3600 && rm -f /tmp/mpd.norandom
MPD_RANDOM_SUSPEND_FILE = os.getenv('MPD_RANDOM_SUSPEND_FILE')
if MPD_RANDOM_SUSPEND_FILE is None:
    MPD_RANDOM_SUSPEND_FILE = os.path.join(tempfile.gettempdir(), 'mpd.norandom')

# Album queue file. This file contains any number of lines. When an album is selected
# lines are processed in order; any match against the album names in the current playlist
# cause that album to be selected next. Lines are consumed as processed until the file is
# empty, after which the file is deleted.
MPD_RANDOM_ALBUM_QUEUE_FILE = os.getenv('MPD_RANDOM_ALBUM_QUEUE_FILE')
if MPD_RANDOM_ALBUM_QUEUE_FILE is None:
    if os.path.exists(os.path.join(os.getenv('HOME'), '.config', 'mpd')):
        MPD_RANDOM_ALBUM_QUEUE_FILE = os.path.join(os.getenv('HOME'), '.config', 'mpd', 'mpd.albumq')
    elif os.path.exists(os.path.join(os.getenv('HOME'), '.mpd')):
        MPD_RANDOM_ALBUM_QUEUE_FILE = os.path.join(os.getenv('HOME'), '.mpd', 'mpd.albumq')
    else:
        MPD_RANDOM_ALBUM_QUEUE_FILE = os.path.join(tempfile.gettempdir(), 'mpd.albumq')

# The archive file, derived from the album queue file. Maintains a history of the albumq. 
# Set to '' via environment variable to disable.
MPD_RANDOM_ALBUM_QUEUE_ARCHIVE_FILE = os.getenv('MPD_RANDOM_ALBUM_QUEUE_ARCHIVE_FILE')
if MPD_RANDOM_ALBUM_QUEUE_ARCHIVE_FILE is None:
    MPD_RANDOM_ALBUM_QUEUE_ARCHIVE_FILE = MPD_RANDOM_ALBUM_QUEUE_FILE + '.archive'

# This is used for testing purposes
PASSIVE_MODE = False


def script_help():
    print(__doc__)
    sys.exit(-1)


def song_info(song):
    """A helper to format song info.
    """
    try:
        return "[{}-{}-{}]".format(song['track'], song['title'], song['album'])
    except:
        return "[{}-{}]".format(song['artist'], song['album'])


def idle_loop(client, albumlist):
    """MPD idle loop.  Used when we're in daemon mode.
    """
    time_song_start = time.time()
    while 1:
        logging.debug("idle_loop: current song: {}".format(client.currentsong()))
        try:
            prevsong = client.currentsong()
            at_last_song = albumlist.is_last_song_in_album(prevsong)
            reasons = client.idle('player','playlist') # blocking
            logging.debug("idle_loop wakeup: response from client.idle: {}".format(str(reasons)))

            # streams come in with ['playlist', 'player'] on song change
            # (with mopidy it is just 'player')
            # we only want to refresh the albumlist if only the playlist has changed:
            if len(reasons) == 1 and 'playlist' in reasons:
                # the playlist has changed
                albumlist.refresh()
                continue

            if not at_last_song:
                # Ignore everything unless we were at the last song on the current album.
                # This is a hack so that we ignore the user changing the playlist. We're
                # trying to detect the end of the album.  The hole here is that if the
                # user changes the current song during the last song on an album then
                # we'll randomly select a new album for them. Unfortunately I don't see how
                # to avoid this given the current MPD API.
                continue

            currsong = client.currentsong()
            if currsong == None or len(currsong) < 1:
                # handle end of playlist
                logging.info("end of playlist detected")
                albumlist.play_next_album(prevsong['album'])
            elif currsong['pos'] != prevsong['pos']:
                logging.debug("song change detected: prev: {} curr: {}".format(song_info(prevsong), song_info(currsong)))
                if currsong['album'] != prevsong['album']:
                    # Check that we are at the end of the last song. This is to handle the case where the user
                    # changes the current song when we're at the last song in an album
                    if 'time' in prevsong:
                        time_elapsed = time.time() - time_song_start
                        song_length = int(prevsong['time'])
                        time_diff = song_length - time_elapsed
                        if abs(time_diff) < 5 or abs(time_diff) > song_length:
                            logging.debug("album changed detected: prev: {0} curr: {1}, time_diff: {2}-{3}={4}".format(prevsong['album'],
                                currsong['album'], song_length, time_elapsed, time_diff))
                            albumlist.play_next_album(prevsong['album'])
                        else:
                            logging.debug("user changed song at end of album; not selecting a different album, time_diff: {0}-{1}={2}".format(song_length,
                                time_elapsed, time_diff))
                    else:
                        albumlist.play_next_album(prevsong['album'])
                # update the start time for the next song
                time_song_start = time.time()

        except:
            logging.error("Unexpected error: {}\n{}".format(sys.exc_info()[0], traceback.format_exc()))
            albumlist.play_next_album()


def connect_mpd():
    """Connect to mpd.
    """
    client = mpd.MPDClient()
    mpd_passwd = None
    mpd_host = os.getenv('MPD_HOST')
    if mpd_host is None:
        mpd_host = 'localhost'
    else:
        splithost = mpd_host.split('@')
        if len(splithost) > 1:
            mpd_passwd = splithost[0]
            mpd_host = splithost[1]
    mpd_port = os.getenv('MPD_PORT')
    if mpd_port is None:
        mpd_port = 6600
    client.connect(mpd_host, mpd_port)
    if mpd_passwd is not None:
        client.password(mpd_passwd)
    logging.debug("MPD version: {}".format(client.mpd_version))
    #logging.debug("client.commands(): %s" % client.commands())
    return client


def go_mpd(client, is_daemon):
    """Top-level function, called from main(). Here is where we start to interact with mpd.
    """
    albumlist = AlbumList(client)
    albumlist.refresh()
    if is_daemon:
        idle_loop(client, albumlist)
    else:
        albumlist.play_next_album()
    client.close()
    client.disconnect()


def mpd_info(client):
    """Print some basic info obtained from mpd.
    """
    albumlist = AlbumList(client)
    albumlist.refresh()
    print("Album List:\n")
    albumlist.print_debug_info()
    print("\nCurrent Song:\n")
    currsong = client.currentsong()
    print(currsong)
    client.close()
    client.disconnect()


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hDpdi", ["help", "debug", "passive", "daemon", "info"])
    except getopt.GetoptError:
        # print help information and exit:
        script_help()
        return 2
    arg_daemon=False
    arg_loglevel = logging.INFO
    arg_info = False
    for o, a in opts:
        if o in ("-h", "--help"):
            script_help()
        elif o in ("-D", "--debug"):
            arg_loglevel = logging.DEBUG
        elif o in ("-p", "--passive"):
            global PASSIVE_MODE
            PASSIVE_MODE = True
        elif o in ("-i", "--info"):
            arg_info = True
        elif o in ("-d", "--daemon"):
            arg_daemon = True
    # configure logging
    logging.basicConfig(level=arg_loglevel)
    client = connect_mpd()
    if PASSIVE_MODE:
        print("PASSIVE_MODE: will not change playlist")
    if arg_info:
        return mpd_info(client)
    go_mpd(client, arg_daemon)
    return 0


class AlbumList:
    """Manages album information as queried from MPD.
    """
    def __init__(self, client):
        self._client = client
        self._pl_info = []
        self._albums = []
        self._last_song_pos = {}
        self._first_song_pos = {}
        if not os.path.exists(MPD_RANDOM_ALBUM_QUEUE_FILE):
            logging.info("Creating album queue file '{}'".format(MPD_RANDOM_ALBUM_QUEUE_FILE))
            self._write_album_queue([])

    def _parse_playlist_info(self):
        """Returns a list of albums from the playlist info."""
        # self._pl_info is a list of:
        #{'file': 'file:///mnt/htpc/store/music/collection/rips/uber/Bob%20Dylan%20-%201966%20-%20Blonde%20on%20Blonde/01%20-%20Rainy%20Day%20Women%20%2312%20%26%2035.mp3', 'time': '276', 'artist': 'Bob Dylan', 'album': 'Blonde on Blonde', 'title': 'Rainy Day Women #12 & 35', 'date': '1966', 'track': '1', 'pos': '140', 'id': '9164', 'genre': 'Folk'}, 
        #logging.debug("playlistinfo: {}".format(self._pl_info))

        last_entry = None
        for pl_entry in self._pl_info:
            try:
                if pl_entry['album'] not in self._albums:
                    self._albums.append(pl_entry['album'])
                    if last_entry:
                        # pick pos from last entry that is returned
                        self._last_song_pos[last_entry['album']] = last_entry['pos']
                        self._first_song_pos[pl_entry['album']] = pl_entry['pos']
                else:
                    last_entry = pl_entry
            except KeyError:
                logging.debug("_parse_playlist_info, no album key, ignoring entry: {}".format(pl_entry))

    def _choose_random_album(self, current_album_name):
        """Selects a random album from the current playlist, doing its best to avoid choosing
        the current album.
        """
        if len(self._albums) < 1:
            logging.warn("No albums found")
            album_name = current_album_name
        elif len(self._albums) == 1:
            logging.debug("only one album found: {}".format(self._albums))
            album_name = self._albums[0]
        else:
            for i in range(0,3):
                # pick a random album from the list of album names we've built
                new_album_index = random.choice(range(0, len(self._albums) - 1))
                album_name = self._albums[new_album_index]
                # If we've picked the same album as current then
                # lets keep trying (a few times before giving up)
                if album_name != current_album_name:
                    break
        logging.info("picked album: {}".format(album_name))
        return album_name

    def _write_album_queue(self, album_q_list):
        """Writes the given album queue to file. Will write an empty file if list is empty."""
        logging.debug("Album queue: writing '{}'".format(MPD_RANDOM_ALBUM_QUEUE_FILE))
        with open(MPD_RANDOM_ALBUM_QUEUE_FILE, 'w') as f:
            for l in album_q_list:
                f.write(l)

    def _write_album_queue_archive(self, album_name):
        """Writes the given album name to the archive file."""
        if MPD_RANDOM_ALBUM_QUEUE_ARCHIVE_FILE is not None and MPD_RANDOM_ALBUM_QUEUE_ARCHIVE_FILE != '':
            logging.debug("Album queue archive: writing '{}'".format(album_name))
            with open(MPD_RANDOM_ALBUM_QUEUE_ARCHIVE_FILE, 'a') as f:
                f.write(album_name + '\n')

    def _process_album_queue(self):
        """Process the album queue file. Selects a matching album from the queue, or returns None if not found."""
        if not os.path.exists(MPD_RANDOM_ALBUM_QUEUE_FILE):
            logging.warn("Album queue file does not exist '{}'".format(MPD_RANDOM_ALBUM_QUEUE_FILE))
            return None
        logging.info("Album queue: Scanning '{}'".format(MPD_RANDOM_ALBUM_QUEUE_FILE))
        with open(MPD_RANDOM_ALBUM_QUEUE_FILE) as f:
            album_q_list = f.readlines()
        if len(album_q_list) < 1:
            return None
        try:
            while len(album_q_list) > 0:
                queued_album = album_q_list.pop(0).strip()
                for album_name in self._albums:
                    if queued_album.startswith('!'):
                        # exact match
                        if queued_album.lstrip('!') == album_name:
                            logging.info("Album queue: exact matched '{}'".format(queued_album))
                            self._write_album_queue_archive(queued_album)
                            return album_name
                    else:
                        # substring match (default)
                        if queued_album in album_name:
                            logging.info("Album queue: matched '{}' in '{}".format(queued_album, album_name))
                            self._write_album_queue_archive(queued_album)
                            return album_name
        finally:
            self._write_album_queue(album_q_list)
        logging.info("Album queue: No matching album found from '{}'".format(MPD_RANDOM_ALBUM_QUEUE_FILE))
        return None

    def refresh(self):
        """Refreshes the album list.
        """
        logging.info("Resyncing from the current playlist")
        self._pl_info = self._client.playlistinfo()
        self._parse_playlist_info()

    def get_album_names(self):
        """Returns list of album names.
        """
        return self._albums

    def is_last_song_in_album(self, currentsong):
        """Given a song entry, returns 1 if song is last in album.
        """
        if currentsong == None or len(currentsong) < 1:
            return False
        if 'album' not in currentsong:
            logging.info("current song has no album, ignoring: {}".format(currentsong))
            return False
        try:
            if currentsong['pos'] == self._last_song_pos[currentsong['album']]:
                logging.info("is last song: {}".format(song_info(currentsong)))
                return True
        except KeyError:
            logging.error("Caught KeyError current pos: {}, currentsong['album']: {}".format(currentsong['pos'],
                                                                                             currentsong['album']))
            return False
        logging.debug("not last song: {}, current pos: {} / last pos: {}".format(song_info(currentsong),
                                                                                 currentsong['pos'],
                                                                                 self._last_song_pos[currentsong['album']]))
        return False

    def play_next_album(self, current_album_name=None):
        """Plays a random album on the current playlist.
        """
        if os.path.exists(MPD_RANDOM_SUSPEND_FILE):
            logging.info("Suspended by presence of {}, not choosing next album".format(MPD_RANDOM_SUSPEND_FILE))
            return
        # choose next album, either by album queue or random
        album_name = self._process_album_queue()
        if album_name is None:
            album_name = self._choose_random_album(current_album_name)
        if album_name is None:
            print("ERROR: could not find an album to play")
            return
        if not album_name in self._albums:
            print("ERROR: could not find album in stored list")
            return
        first_song_pos = self._first_song_pos[album_name]
        logging.debug("found first_song_pos: {}".format(first_song_pos))
        if not first_song_pos:
            print("ERROR: could not find first_song_pos for album '{}'".format(album_name))
            return
        if not PASSIVE_MODE:
            self._client.play(first_song_pos)

    def print_debug_info(self):
        print("Albums: {}".format(self._albums))
        print("Last Song Positions: {}".format(self._last_song_pos))


###############################################################################
if __name__ == "__main__" or __name__ == "main":
    sys.exit(main())
###############################################################################

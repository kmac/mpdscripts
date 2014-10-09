#!/usr/bin/env python2

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
is arranged as a list of albums. It's meant to provide a rudimentary album
shuffle function for MPD.

In daemon mode the script will monitor MPD and select a new album
in the playlist after the last song on an album has ended (see -d option).

Options:
   -h|--help
   -d|--daemon  : daemon mode. Monitor MPD for track changes. At end of album select
                  a new random album from the playlist
   -D|--debug   : Print debug messages to stdout
   -p|--passive : testing only. Don't make any changes to the MPD playlist

Dependencies:
   python-mpd

Limitations:
   The album switching is currently triggered when the last song on an album
   is reached.  If the user changes the current song selection during
   the last song on an album then this script will kick in, randomly
   selecting a new album.  Unfortunately I don't see how to avoid this
   unless we were to time how long the last song has been playing for, and
   compare it to the song length given by MPD.

Other Usage Notes:
-----------------
mpd.norandom file
When file <TEMPDIR>/mpd.norandom exists, the script does not perform album selection.
You can use this to temporarily override the functionality when the script is running
in daemon mode.

e.g. touch /tmp/mpd.norandom
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

# This is used for testing purposes
PASSIVE_MODE = False

# If this file exists then no random album is chosen. Used to easily disable the daemon
# e.g. touch /tmp/mpd.norandom && sleep 3600 && rm -f /tmp/mpd.norandom
SUSPEND_FILENAME = os.path.join(tempfile.gettempdir(), 'mpd.norandom')


def script_help():
    print __doc__
    sys.exit(-1)


def song_info(song):
    """A helper to format song info.
    """
    try:
        return "[%s-%s-%s]" % (song['track'],song['title'],song['album'])
    except:
        return "[%s-%s]" % (song['artist'],song['album'])


def idle_loop(client, albumlist):
    """MPD idle loop.  Used when we're in daemon mode.
    """
    time_song_start = time.time()
    while 1:
        try:
            prevsong = client.currentsong()
            at_last_song = albumlist.is_last_song_in_album(prevsong)
            reasons = client.idle('player','playlist') # blocking
            if 'playlist' in reasons:
                # the playlist has changed
                albumlist.refresh()
                continue
            if not at_last_song:
                # ignore everything unless we were at the last song on the current album.
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
                albumlist.play_random_album(prevsong['album'])
            elif currsong['pos'] != prevsong['pos']:
                logging.debug("song change detected: prev: %s curr: %s" % (song_info(prevsong), song_info(currsong)))
                if currsong['album'] != prevsong['album']:
                    # Check that we are at the end of the last
                    # song. This is to handle the case where the user
                    # changes the current song when we're at the last
                    # song in an album
                    time_elapsed = time.time() - time_song_start
                    song_length = int(prevsong['time'])
                    time_diff = song_length - time_elapsed
                    if abs(time_diff) < 5 or abs(time_diff) > song_length:
                        logging.debug("album changed detected: prev: %s curr: %s, time_diff: %s-%s=%s" % (prevsong['album'],currsong['album'], song_length, time_elapsed, time_diff))
                        albumlist.play_random_album(prevsong['album'])
                    else:
                        logging.debug("user changed song at end of album.  not selecting a different album, time_diff: %s-%s=%s" % (song_length, time_elapsed, time_diff))
                # update the start time for the next song
                time_song_start = time.time()
        except:
            logging.error("Unexpected error: %s\n%s" % (sys.exc_info()[0], traceback.format_exc()))
            albumlist.play_random_album()


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
    logging.debug("MPD version: %s" % client.mpd_version)
    #logging.debug("client.commands(): %s" % client.commands())
    return client


def go_mpd(client, daemon):
    """Top-level function, called from main(). Here is where we start to interact with mpd.
    """
    albumlist = AlbumList(client)
    albumlist.refresh()
    if daemon:
        idle_loop(client, albumlist)
    else:
        albumlist.play_random_album()
    client.close()
    client.disconnect()


def mpd_info(client):
    """Print some basic info obtained from mpd.
    """
    albumlist = AlbumList(client)
    albumlist.refresh()
    print "Album List:\n"
    albumlist.print_debug_info()
    print "\nCurrent Song:\n"
    currsong = client.currentsong()
    print(currsong)
    client.close()
    client.disconnect()


def main():
    daemon=0
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hDpdi", ["help", "debug", "passive", "daemon", "info"])
    except getopt.GetoptError:
        # print help information and exit:
        script_help()
        return 2
    loglevel = logging.INFO
    info = 0
    for o, a in opts:
        if o in ("-h", "--help"):
            script_help()
        elif o in ("-D", "--debug"):
            loglevel = logging.DEBUG
        elif o in ("-p", "--passive"):
            global PASSIVE_MODE
            PASSIVE_MODE = True
        elif o in ("-i", "--info"):
            info = 1
        elif o in ("-d", "--daemon"):
            daemon = 1
    # configure logging
    logging.basicConfig(level=loglevel)
    client = connect_mpd()
    if PASSIVE_MODE:
        print "PASSIVE_MODE: will not change playlist"
    if info:
        return mpd_info(client)
    go_mpd(client, daemon)
    return 0


class AlbumList:
    """Manages album information as queried from MPD.
    """
    def __init__(self, client):
        self._client = client

    def _create_album_list(self, plinfo):
        """Returns a list of albums from the playlist info."""
        self._albums = []
        for a in plinfo:
            try:
                if a['album'] not in self._albums:
                    self._albums.append(a['album'])
            except KeyError:
                logging.debug("createAlbumList, no album key, ignoring entry: %s" % a)

    def _create_last_song_list(self, plinfo):
        """Manages the _last_song_pos map, which maintains a last song position for each album.
        """
        self._last_song_pos = {}
        for a in self._albums:
            entries = self._client.playlistfind("album", a)

            # skip if size of entries is zero
            if len(entries) == 0:
                continue
            elif len(entries) == 1:
                logging.debug("Single file album=%s: %s" % (a, song_info(entries[-1])))
            else:
                logging.debug("Last song for album=%s: %s" % (a, song_info(entries[-1])))

            # pick pos from last entry that is returned
            self._last_song_pos[a] = entries[-1]['pos']

    def _choose_random_album(self, current_album_name):
        """Picks a random album from the current playlist, doing its best to avoid choosing
        the current album.
        """
        if len(self._albums) < 1:
            logging.warn("No albums found")
            album_name = current_album_name
        elif len(self._albums) == 1:
            logging.debug("only one album found: %s" % self._albums)
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
        logging.info("picked album: %s" % (album_name))
        return album_name

    def refresh(self):
        """Refreshes the album list.
        """
        plinfo = self._client.playlistinfo()
        self._create_album_list(plinfo)
        self._create_last_song_list(plinfo)

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
            logging.info("current song has no album, ignoring: %s" % currentsong)
            return False
        if currentsong['pos'] == self._last_song_pos[currentsong['album']]:
            logging.info("is last song: %s" % song_info(currentsong))
            return True
        logging.debug("not last song: %s, current pos: %s / last pos: %s" % (song_info(currentsong), currentsong['pos'], self._last_song_pos[currentsong['album']]))
        return False

    def play_random_album(self, current_album_name=None):
        """Plays a random album on the current playlist.
        """
        if os.path.exists(SUSPEND_FILENAME):
            logging.info("Suspended by presence of %s, not choosing random album" % SUSPEND_FILENAME)
            return
        album_name = self._choose_random_album(current_album_name)
        if album_name == None:
            print "ERROR: could not find an album to play"
            return
        # Look for tracks in album.  They are ordered by position in the playlist.
        # NOTE: if the playlist is not sorted by album the results may be wonky.
        entries = self._client.playlistfind("album", album_name)
        if len(entries) < 1:
            print "ERROR: could not find album '%s'" % album_name
            return
        logging.debug("found entry: %s" % entries[0])
        if not PASSIVE_MODE:
            # play at the playlist position of the first returned entry
            self._client.play(entries[0]['pos'])

    def print_debug_info(self):
        print "Albums: %s" % self._albums
        print "Last Song Positions: %s" % self._last_song_pos


###############################################################################
if __name__ == "__main__" or __name__ == "main":
    sys.exit(main())
###############################################################################

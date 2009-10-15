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
This script picks a random album from the MPD playlist.  Called with no
args it will pick a random album from the current playlist and start
playing.

It can also monitor MPD and select a new album in the playlist after the
last song on an album has ended. Use the -d option

Options:
   -h|--help
   -d|--daemon  : daemon.  Monitor MPD for track changes. At end of album select 
                  a new random album from the playlist
   -D|--debug   : Print debug messages to stdout
   -p|--passive : testing only. Don't make any changes to the MPD playlist

Requires:
   python-mpd
"""

import getopt
import mpd
import random
import sys

DEBUG=1
PASSIVE_MODE=0
    
def debug(str):
    global DEBUG
    if DEBUG == 1:
        print >> sys.stderr, 'DEBUG: %s' % str

def scriptHelp():
    print __doc__
    sys.exit(-1)

def songInfo(song):
    """ a helper """
    return "[%s-%s-%s]" % (song['track'],song['title'],song['album'])


class AlbumList:
    "Manages album information as queried from MPD"
    def __init__(self, client):
        self._client = client

    def _createAlbumList(self, plinfo):
        "returns a list of albums from the playlist info"
        self._albums = []
        for a in plinfo:
            if a['album'] not in self._albums:
                self._albums.append(a['album'])

    def _createLastSongList(self, plinfo):
        " manages the _lastsongpos map, which maintains a last song position for each album "
        self._lastsongpos = {}
        for a in self._albums:
            entries = self._client.playlistfind("album", a)
            # pick pos from last entry that is returned
            self._lastsongpos[a] = entries[len(entries)-1]['pos']
            debug("Last song for album=%s: %s" % (a, songInfo(entries[len(entries)-1])))
            
    def _chooseRandomAlbum(self, currentAlbumName):
        """ picks a random album from the current playlist, doing
            its best to avoid choosing the current album """
        if len(self._albums) < 1:
            debug("No albums found")
            albumName = currentAlbumName
        elif len(self._albums) == 1:
            debug("only one album found: %s" % self._albums)
            albumName = self._albums[0]
        else:
            for i in range(0,3):
                # pick a random album from the list of album names we've built
                newalbumindex = random.choice(range(0, len(self._albums) - 1))
                albumName = self._albums[newalbumindex]
                # If we've picked the same album as current then
                # lets keep trying (a few times before giving up)
                if albumName != currentAlbumName:
                    break
        debug("picked album: %s" % (albumName))
        return albumName

    def refresh(self):
        " refreshes the album list "
        plinfo = self._client.playlistinfo()
        self._createAlbumList(plinfo)
        self._createLastSongList(plinfo)

    def getAlbumNames(self):
        " returns list of album names "
        return self._albums

    def isLastSongInAlbum(self, currentsong):
        " given a song entry, returns 1 if song is last in album "
        if currentsong == None or len(currentsong) < 1:
            return 0
        if currentsong['pos'] == self._lastsongpos[currentsong['album']]:
            debug("is last song: %s" % songInfo(currentsong))
            return 1
        debug("NOT last song: %s, last pos: %s" % (songInfo(currentsong), self._lastsongpos[currentsong['album']]))
        return 0

    def playRandomAlbum(self, currentAlbumName=None):
        " plays a random album on the current playlist "
        albumName = self._chooseRandomAlbum(currentAlbumName)
        if albumName == None:
            print "ERROR: could not find an album to play"
            return 0
        # Look for tracks in album.  They are ordered by position in the playlist.
        # NOTE: if the playlist is not sorted by album the results may be wonky.
        entries = self._client.playlistfind("album", albumName)
        if len(entries) < 1:
            print "ERROR: could not find album '%s'" % albumName
            return 0
        debug("found entry: %s" % entries[0])
        if not PASSIVE_MODE:
            # play at the playlist position of the first returned entry
            self._client.play(entries[0]['pos'])
        return 1

    def printDebugInfo(self):
        debug("Albums: %s" % self._albums)
        debug("Last Song Positions: %s" % self._lastsongpos)


def idleLoop(client, albumlist):
    """ MPD idle loop.  Used when we're in daemon mode """
    while 1:
        prevsong = client.currentsong()
        atlastsong = albumlist.isLastSongInAlbum(prevsong)
        reasons = client.idle('player','playlist') # blocking
        if 'playlist' in reasons:
            # the playlist has changed
            albumlist.refresh()
            continue
        if not atlastsong:
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
            debug("end of playlist detected")
            albumlist.playRandomAlbum(prevsong['album'])
        elif currsong['pos'] != prevsong['pos']:
            debug("song change detected: prev: %s curr: %s" % (songInfo(prevsong), songInfo(currsong)))
            if currsong['album'] != prevsong['album']:
                debug("album changed detected: prev: %s curr: %s" % (prevsong['album'],currsong['album']))
                albumlist.playRandomAlbum(prevsong['album'])


def goMpd(daemon):
    client = mpd.MPDClient()
    client.connect("localhost", 6600)
    debug("MPD version: %s" % client.mpd_version)
    #debug("client.commands(): %s" % client.commands())
    albumlist = AlbumList(client)
    albumlist.refresh()
    if daemon:
        idleLoop(client, albumlist)
    else:
        albumlist.playRandomAlbum()
    client.close()
    client.disconnect()


def main():
    daemon=0
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hDpd", ["help", "debug", "passive", "daemon"])
    except getopt.GetoptError:
        # print help information and exit:
        scriptHelp()
        return 2
    argMode='directory'
    for o, a in opts:
        #debug("o=%s a=%s" % (o, a))
        if o in ("-h", "--help"):
            scriptHelp()
        elif o in ("-D", "--debug"):
            global DEBUG
            DEBUG = 1
        elif o in ("-p", "--passive"):
            global PASSIVE_MODE
            PASSIVE_MODE = 1
        elif o in ("-d", "--daemon"):
            daemon = 1
    #
    if PASSIVE_MODE:
        print "PASSIVE_MODE: will not change playlist"
    goMpd(daemon)
    return 0

###############################################################################
if __name__ == "__main__" or __name__ == "main":
    sys.exit(main())
###############################################################################

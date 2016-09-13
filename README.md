mpdscripts
==========

Some scripts to interact with MPD.


mpd-random-playlist-album.py
============================
A python script which plays a random album from the current MPD playlist.
It can also be run as a daemon, where at the end of an album it will select
a new album from the current playlist to play; It does this by monitoring track changes,
detecting the end of an album.

The basic idea of this script is to load up the playlist with albums,
then run this script as a daemon. When one album finishes, a new album will be chosen at random from the playlist.
Similar to Amarok's album shuffle mode or foobar2000's random album mode.


The following is taken from the help:

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

This is a way to queue up individual albums to be played in order.  You can put
album titles in /tmp/mpd.albumq, one line per album.  Album names are
consumed as a queue, until the file is empty, after which the selector will
revert back to random. 

By default, the given album string matches the first album against any
substring in the playlist album names (case-sensitive). For an exact match,
prefix the album name with a '!'.

An example /tmp/mpd.albumq:

    Abbey Road
    !Movement (Remastered)


### mpd.norandom file

When file /tmp/mpd.norandom exists, the script does not perform album selection.

You can use this to temporarily override the functionality when the script is running
in daemon mode. e.g.:

    touch /tmp/mpd.norandom


Examples
--------

Select a new album to play from the current playlist:

    ./mpd-random-playlist-album.py

Start a daemon, logging output to /tmp/mpd-random-playlist-album.log

    (./mpd-random-playlist-album.py -d > /tmp/mpd-random-playlist-album.log 2>&1 ) &



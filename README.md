mpdscripts
==========

MPD scripts


mpd-random-pl-album.py
----------------------
A python script which plays a random album from the current MPD playlist. 
It can also be run as a daemon, where at the end of an album it will select 
a new album from the current playlist to play; It does this by monitoring track changes,
detecting the end of an album. 

The basic idea of this script is to load up the playlist with albums, 
then run this script as a daemon. When one album finishes, a new album will be chosen at random from the playlist. 
Similar to Amarok's album shuffle mode or foobar2000's random album mode.


Depends: python-mpd

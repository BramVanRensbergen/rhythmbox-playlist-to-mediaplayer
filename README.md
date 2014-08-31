Rhythmbox-Playlists-To-MediaPlayer
==========================

A tool to sync the songs in your rhythmbox playlists, and the playlists themselves, to a separate directory (e.g., a media player or cellphone).

Author: Bram Van Rensbergen <mail@bramvanrensbergen.com>


This tool is based on Kyle Dickerson's <a href = "https://github.com/kdickerson/Rhythmbox-Playlists-Export">Rhythmbox-Playlists-Export</a>. 

The most important change is that ONLY files contained in the playlists you are syncing, are copied; other local media files are ignored. Rsync functionality was removed as well.
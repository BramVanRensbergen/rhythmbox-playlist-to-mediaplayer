#! /usr/bin/env python

# Author: Bram Van Rensbergen
# email: mail@bramvanrensbergen.com
# last modified: August, 2014

import dbus
import os
import glob
import re
import urllib
import time
from xml.etree.ElementTree import Element, ElementTree
import logging
logging.basicConfig(level=logging.DEBUG) # filename='example.log',
# Assumes base paths of local and remote media do not have special characters
#  Rhythmbox uses some form of URI encoding that doesn't match what urllib.quote() gives you
#  So until I can figure out how to reliably replicate their quoting scheme, this won't support special characters in the base paths

logging.info("Beginning Sync")

# Need to be configured
local_username = 'decius'
local_media = ["/media/media/Music"] #["/home/%s/%s" % (local_username, x) for x in ["Music", "Audiobooks", "Podcasts"]]
local_playlists = '/home/decius/music_sync/temp' #'/tmp/rhythmbox_sync'
remote_media = "/home/decius/music_sync/'"
remote_playlists = '/home/decius/music_sync/playlists/'

EXPORT_PLAYLISTS = True
KEEP_LOCAL_PLAYLIST_EXPORT = True
PLAYLIST_FORMAT = 'M3U' # only M3U currently supported, See note about Rhythmbox URI encoding above which also pertains to PLS support
SYNC_PLAYLISTS = True
DRY_RUN = False # Don't actually rsync anything

# Probably correct from above configuration
local_media_bases = [x[:x.rfind('/')] for x in local_media]
rhythmbox_startup_wait = 15 #15 seconds, if Rhythmbox hasn't finished initializing the exports won't work (haven't found a programmatic way to check this)
rhythmbox_shutdown_wait = 3 # seconds
skip_playlists = ['Recently Added', 'Recently Played', 'My Top Rated', 'check', 'cd']

if not os.path.exists(local_playlists):
  logging.info("Creating directory for local export")
  os.makedirs(local_playlists)

def export_playlists():
  logging.info("Exporting playlists...")
  clean_names_regex = re.compile(r'[^\w\s]')
  sessionBus = dbus.SessionBus()
  playlistManager = sessionBus.get_object('org.gnome.Rhythmbox3', '/org/gnome/Rhythmbox3/PlaylistManager')
  asM3U = (PLAYLIST_FORMAT == 'M3U')
  logging.debug("asM3U: %s" % (asM3U))
  for playlistName in playlistManager.GetPlaylists(dbus_interface='org.gnome.Rhythmbox3.PlaylistManager'):
    if playlistName in skip_playlists: continue
    filename = "%s.%s" % (re.sub(clean_names_regex, '_', playlistName), PLAYLIST_FORMAT.lower())
    logging.info("Exporting '%s' to '%s'" % (playlistName, filename))
    try:
      fileURI = 'file://%s/%s' % (local_playlists, filename)
      logging.debug("URI: %s" % (fileURI))
      playlistManager.ExportPlaylist(playlistName, fileURI, asM3U, dbus_interface='org.gnome.Rhythmbox3.PlaylistManager')
    except dbus.exceptions.DBusException as ex:
      logging.error("Failed to export playlist: %s" % (playlistName))
      if ex.get_dbus_name().find('Error.NoReply') > -1:
        logging.error("Perhaps it was empty?  Attempting to restart Rhythmbox...")
        os.system('rhythmbox-client --no-present')
        logging.info('Pausing %d seconds for Rhythmbox initialization' % (rhythmbox_startup_wait))
        time.sleep(rhythmbox_startup_wait) # rhythmbox isn't ready until shortly after rhythmbox-client returns
        playlistManager = sessionBus.get_object('org.gnome.Rhythmbox3', '/org/gnome/Rhythmbox3/PlaylistManager')
      else:
        logging.error("%s:%s" % (ex.get_dbus_name(), ex.get_dbus_message()))
        break


def sync_playlists():
  logging.info("Syncing playlists...")
  alterred_playlists = "%s/%s" % (local_playlists, "alterred")
  if not os.path.exists(alterred_playlists):
    os.makedirs(alterred_playlists)
  for filename in glob.glob("%s/*.%s" % (local_playlists, PLAYLIST_FORMAT.lower())):
    playlist = open(filename, 'r')  
    playlist_text = playlist.readlines()
    playlist.close()
    playlist_text_out = []
    for line in playlist_text:
      if line.startswith('#'):
        playlist_text_out.append(line)
        continue
      success = False
      for media_loc in local_media_bases:
        if line.find(media_loc) > -1:
          playlist_text_out.append(line.replace(media_loc, remote_media))
          cmd = 'cp -uv \"%s\" \"%s\"' % (line.rstrip('\n'), remote_media)
         # logging.debug('Executing: %s' % (cmd))
          os.system(cmd)
          #logging.debug(line)
          success = True
          break
      if not success:
        logging.error("Couldn't determine how to modify file location for remote use: %s" % (line))
    playlist_out = open("%s/%s" % (alterred_playlists, filename[filename.rfind('/')+1:]), 'w')
    playlist_out.writelines(playlist_text_out)
    playlist_out.close()
  if not DRY_RUN:
    cmd = 'rsync -vrlptgz -e ssh "%s/"*.%s "%s@%s:%s" --delete-excluded' % (alterred_playlists, PLAYLIST_FORMAT.lower(), "ab", "cd", remote_playlists)
    logging.debug('Executing: %s' % (cmd))
    #os.system(cmd)


if EXPORT_PLAYLISTS:
  os.system('rhythmbox-client --no-present')
  logging.info('Pausing %d seconds for Rhythmbox initialization' % (rhythmbox_startup_wait))
  time.sleep(rhythmbox_startup_wait) # rhythmbox isn't ready until shortly after rhythmbox-client returns
  export_playlists()

if SYNC_PLAYLISTS:
  sync_playlists()

if not KEEP_LOCAL_PLAYLIST_EXPORT:
  logging.info("Removing folder used for local export")
  os.system('rm -rf %s' % (local_playlists))
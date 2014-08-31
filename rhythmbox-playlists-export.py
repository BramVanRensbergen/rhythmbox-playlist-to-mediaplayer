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
import ntpath
from xml.etree.ElementTree import Element, ElementTree
import logging
logging.basicConfig(level=logging.DEBUG) # filename='example.log',
# Assumes base paths of local and remote media do not have special characters
#  Rhythmbox uses some form of URI encoding that doesn't match what urllib.quote() gives you
#  So until I can figure out how to reliably replicate their quoting scheme, this won't support special characters in the base paths

logging.info("Beginning Sync")

# Need to be configured
local_playlists = '/home/decius/Desktop/music/temp_playlists'  #playlists are temporarily stored here (permanently if KEEP_LOCAL_PLAYLIST_EXPORT = true)
destination_media = "/home/decius/Desktop/music/"              #files are exported to this directory
destination_playlists = '/home/decius/Desktop/music/Playlists' #playlists with new paths are stored here 
skip_playlists = ['Recently Added', 'Recently Played', 'My Top Rated', 'check'] #Skip these playlists
sync_playlists = ['altrock', 'chill'] #ONLY sync these playlists; if this is empty, sync ALL playlists except those in skip_playlists


KEEP_LOCAL_PLAYLIST_EXPORT = True
PLAYLIST_FORMAT = 'M3U' # only M3U currently supported, See note about Rhythmbox URI encoding above which also pertains to PLS support
rhythmbox_startup_wait = 1 #15 seconds, if Rhythmbox hasn't finished initializing the exports won't work (haven't found a programmatic way to check this)


def rhythmbox_playlists_export():
    #create folders if necessary
    if not os.path.exists(destination_media):
        logging.info("Creating directory for destination media")
        os.makedirs(destination_media)
    
    if not os.path.exists(destination_playlists):
        logging.info("Creating directory for destination playlists")
        os.makedirs(destination_playlists)
    
    if not os.path.exists(local_playlists):
        logging.info("Creating directory for local export")
        os.makedirs(local_playlists)

    #export rhythmbox playlists  
    os.system('rhythmbox-client --no-present')
    logging.info('Pausing %d seconds for Rhythmbox initialization' % (rhythmbox_startup_wait))
    time.sleep(rhythmbox_startup_wait) # rhythmbox isn't ready until shortly after rhythmbox-client returns
    export_playlists()

    #copy all files in those playlists to destination dir, and export edited version of the playlists refering to the new source
    sync_playlist_media()

    #cleanup
    if not KEEP_LOCAL_PLAYLIST_EXPORT:
      logging.info("Removing folder used for local export")
      os.system('rm -rf %s' % (local_playlists))
  

def export_playlists():
  logging.info("Exporting playlists...")
  clean_names_regex = re.compile(r'[^\w\s]')
  sessionBus = dbus.SessionBus()
  playlistManager = sessionBus.get_object('org.gnome.Rhythmbox3', '/org/gnome/Rhythmbox3/PlaylistManager')
  asM3U = (PLAYLIST_FORMAT == 'M3U')
  for playlistName in playlistManager.GetPlaylists(dbus_interface='org.gnome.Rhythmbox3.PlaylistManager'):
    
    #check whether we have to sync this playlist!
    syncThis = True
    if len(sync_playlists) > 0 and not playlistName in sync_playlists: syncThis = False #working with whitelist, and this playlist is not on it
    if playlistName in skip_playlists: syncThis = False #playlist is on blacklist, skip it
    
    if not syncThis:
        logging.info('Skipping %s' %playlistName)
        continue
    
    #Try to sync the playlist
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


def sync_playlist_media():
  logging.info("Syncing playlists and media...")
  for filename in glob.glob("%s/*.%s" % (local_playlists, PLAYLIST_FORMAT.lower())):
    playlist = open(filename, 'r')  
    playlist_text = playlist.readlines()
    playlist.close()
    playlist_text_out = []
    for line in playlist_text:
      if line.startswith('#'):
        playlist_text_out.append(line) #copy comment lines as is
        continue
      source_path = line.rstrip('\n')      
      fname = path_leaf(source_path)
      dest_path = destination_media + fname #path that file will have in destination
      
      #add converted path to new playlist
      playlist_text_out.append(dest_path + '\n') 
      
      #copy file to destination!
      cmd = 'cp -u \"%s\" \"%s\"' % (source_path, destination_media)
      logging.info('Executing: %s' % (cmd))
      os.system(cmd)

    playlist_out = open("%s/%s" % (destination_playlists, filename[filename.rfind('/')+1:]), 'w')
    playlist_out.writelines(playlist_text_out)
    playlist_out.close()

#return the last part of a path (generally, the filename)
def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

rhythmbox_playlists_export()

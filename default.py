#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import threading
import xbmc
import xbmcaddon
import unicodedata
import json
import time
from datetime import datetime
import xbmcgui
import urllib2

__addon__         = xbmcaddon.Addon()
__cwd__           = __addon__.getAddonInfo('path')
__icon__          = __addon__.getAddonInfo("icon")
__scriptname__    = __addon__.getAddonInfo('name')
__version__       = __addon__.getAddonInfo('version')
__language__      = __addon__.getLocalizedString
__resource_path__ = os.path.join(__cwd__, 'resources', 'lib')
__resource__      = xbmc.translatePath(__resource_path__).decode('utf-8')

from resources.lib.tvshowtime import FindEpisode
from resources.lib.tvshowtime import IsChecked
from resources.lib.tvshowtime import MarkAsWatched
from resources.lib.tvshowtime import MarkAsUnWatched
from resources.lib.tvshowtime import GetUserInformations
from resources.lib.croniter import croniter

busy = False

class Monitor(xbmc.Monitor):
    
    screensaver_running = False
    
    def __init__( self, *args, **kwargs ):
        xbmc.Monitor.__init__( self )
        self.token = __addon__.getSetting('token')
        self.facebook = __addon__.getSetting('facebook')
        self.twitter = __addon__.getSetting('twitter')
        self.notifications = __addon__.getSetting('notifications')
        self.action = kwargs['action']

    def onDatabaseUpdated(self,database):
        log('onDatabaseUpdated')
        self.after_scan(database)

    def onSettingsChanged(self):
        xbmc.sleep(1000)
        log('onSettingsChanged')
        self.action()
        
    def onScreensaverActivated(self):
        log("onScreensaverActivated")
        self.screensaver_running = True

    def onScreensaverDeactivated(self):
        log("onScreensaverDeactivated")
        self.screensaver_running = False
        
    def onNotification(self, sender, method, data):
        log('onNotification')
        log('method=%s' % method)
        if (method == 'Player.OnPlay'):
            log('Player.OnPlay')
            response = json.loads(data) 
            log('%s' % response)
            if response.get('item').get('type') == 'episode':
                xbmc_id = response.get('item').get('id')
                item = self.getEpisodeTVDB(xbmc_id)    
                log('showtitle=%s' % item['showtitle'])
                log('season=%s' % item['season'])
                log('episode=%s' % item['episode'])
                if len(item['showtitle']) > 0 and item['season'] > 0 and item['episode'] > 0:                   
                    filename = '%s.S%sE%s' % (formatName(item['showtitle']), item['season'], item['episode'])
                    log('tvshowtitle=%s' % filename)
                    episode = FindEpisode(self.token, filename)
                    log('episode.is_found=%s' % episode.is_found)
                    if episode.is_found:
                        if self.notifications:            
                            notif('%s %s %sx%s' % (__language__(32904), episode.showname, episode.season_number, episode.number), time=2500)
                    else:
                        if self.notifications:
                            notif(__language__(32905), time=2500)
                else:
                    if self.notifications:
                        notif(__language__(32905), time=2500)
        if (method == 'VideoLibrary.OnUpdate' and not busy):
            log('VideoLibrary.OnUpdate')
            response = json.loads(data) 
            log('%s' % response)
            if response.get('item').get('type') == 'episode':
                xbmc_id = response.get('item').get('id')
                playcount = response.get('playcount') 
                #log('playcount=%s' % playcount)
                item = self.getEpisodeTVDB(xbmc_id)    
                #log('showtitle=%s' % item['showtitle'])
                #log('season=%s' % item['season'])
                #log('episode=%s' % item['episode'])
                #log('playcount=%s' % playcount)
                if len(item['showtitle']) > 0 and item['season'] > 0 and item['episode'] > 0:
                    filename = '%s.S%sE%s' % (formatName(item['showtitle']), item['season'], item['episode'])
                    log('tvshowtitle=%s' % filename)
                    episode = FindEpisode(self.token, filename)
                    log('episode.is_found=%s' % episode.is_found)
                    if episode.is_found:
                        if playcount is 1:
                            log('MarkAsWatched(*, %s, %s, %s)' % (filename, self.facebook, self.twitter))
                            checkin = MarkAsWatched(self.token, filename, self.facebook, self.twitter)
                            log('checkin.is_marked:=%s' % checkin.is_marked)
                            if checkin.is_marked:
                                if self.notifications:
                                    notif('%s %s %sx%s' % (__language__(32906), episode.showname, episode.season_number, episode.number), time=2500)
                                else:
                                    if self.notifications:
                                        notif(__language__(32907), time=2500)
                        if playcount is 0:
                            log('MarkAsUnWatched(*, %s)' % (filename))
                            checkin = MarkAsUnWatched(self.token, filename)
                            log('checkin.is_unmarked:=%s' % checkin.is_unmarked)
                            if checkin.is_unmarked:
                                if self.notifications:
                                    notif('%s %s %sx%s' % (__language__(32908), episode.showname, episode.season_number, episode.number), time=2500)
                                else:
                                    if self.notifications:
                                        notif(__language__(32907), time=2500)

    def getEpisodeTVDB(self, xbmc_id):
        rpccmd = {'jsonrpc': '2.0', 'method': 'VideoLibrary.GetEpisodeDetails', 'params': {"episodeid": int(xbmc_id), 'properties': ['season', 'episode', 'tvshowid', 'showtitle']}, 'id': 1}
        rpccmd = json.dumps(rpccmd)
        result = xbmc.executeJSONRPC(rpccmd)
        result = json.loads(result)
        
        try:
            item = {}
            item['season'] = result['result']['episodedetails']['season']
            item['tvshowid'] = result['result']['episodedetails']['tvshowid']
            item['episode'] = result['result']['episodedetails']['episode']
            item['showtitle'] = result['result']['episodedetails']['showtitle']
            return item
        except:
            return False
               
# STOLEN from xbmclibraryautoupdate
class AutoUpdater:
    last_run = 0
    sleep_time = 500
    schedules = []
    lock = False
    busy = False
    
    monitor = None
    
    timer_amounts = {}
    timer_amounts['0'] = 1
    timer_amounts['1'] = 2
    timer_amounts['2'] = 4
    timer_amounts['3'] = 6
    timer_amounts['4'] = 12
    timer_amounts['5'] = 24
    
    def __init__(self):
        self.monitor = Monitor(action = None)
        self.token = __addon__.getSetting('token')
        self.notifications = __addon__.getSetting('notifications')
        self.auto_sync = __addon__.getSetting('auto_sync')
        self.startup_delay = __addon__.getSetting('startup_delay')
        self.run_during_playback = __addon__.getSetting('run_during_playback')
        self.run_on_idle = __addon__.getSetting('run_on_idle')
        self.advanced_timer = __addon__.getSetting('advanced_timer')
        self.timer_value = __addon__.getSetting('timer')
        self.advanced = __addon__.getSetting('advanced')
        self.last_run_setting = __addon__.getSetting('last_run')
        self.readLastRun()
        self.createSchedules(True)
        
    def runProgram(self):    
        if(int(self.startup_delay) != 0):
            count = 0
            while count < len(self.schedules):
                if(time.time() > self.schedules[count].next_run):
                    self.schedules[count].next_run = time.time() + int(self.startup_delay) * 60
                count = count + 1
        self.showNotify()
        while(not xbmc.abortRequested):
            if(time.time() > self.last_run + 60):
                self.readLastRun()
                self.evalSchedules()
            xbmc.sleep(self.sleep_time)
        del self.monitor
        
    def evalSchedules(self):
        if(not self.lock):
            now = time.time()
            count = 0
            tempLastRun = self.last_run
            while count < len(self.schedules):
                cronJob = self.schedules[count]
                if(cronJob.next_run <= now):
                    if(xbmc.Player().isPlaying() == False or self.run_during_playback == "true"):
                        if(self.run_on_idle == 'false' or (self.run_on_idle == 'true' and self.monitor.screensaver_running)):
                            if(self._networkUp()):
                                if(cronJob.on_delay == True):
                                    self.schedules[count].next_run = now + 60
                                    self.schedules[count].on_delay = False
                                    log(cronJob.name + " paused due to playback")
                                elif(self.scanRunning() == False and not self.busy):
                                    log(cronJob.name)
                                    if(cronJob.timer_type == 'xbmc'):
                                        log('Sync started')
                                        if self.notifications:
                                            notif('Sync started', time=2500)
                                        self.sync()
                                    cronJob.next_run = self.calcNextRun(cronJob.expression,now)
                                    self.schedules[count] = cronJob
                                elif(self.scanRunning() == True and not self.busy):
                                    self.schedules[count].on_delay = True
                                    log("Waiting for scan to finish")
                                elif(self.scanRunning() == False and self.busy):
                                    self.schedules[count].on_delay = True
                                    log("Waiting for other sync to finish")
                            else:
                                log("Network down, not running")
                        else:
                            log("Skipping scan, only run when idle")
                    else:
                        self.schedules[count].on_delay = True
                        log("Player is running, wait until finished")
                count = count + 1
            now = time.time()
            self.last_run = now - (now % 60)

    def sync(self):
        busy = True
        command = '{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes", "params": { "properties": ["season", "episode", "showtitle", "playcount", "tvshowid"] }, "id": 1}'
        result = json.loads(xbmc.executeJSONRPC(command))                                        
        for i in range(0, result['result']['limits']['total']):
            filename = '%s.S%sE%s' % (formatName(result['result']['episodes'][i]['showtitle']), result['result']['episodes'][i]['season'], result['result']['episodes'][i]['episode'])
            log('tvshowtitle=%s' % filename)
            episode = IsChecked(self.token, filename)
            if episode.is_found:
                log("episode.is_found=%s" % episode.is_found)
                if episode.is_watched == True: episode.is_watched = 1
                else: episode.is_watched = 0
                log("kodi.playcount=%s" % result['result']['episodes'][i]['playcount'])
                log("tvst.playcount=%s" % episode.is_watched)
                if result['result']['episodes'][i]['playcount'] <> episode.is_watched:
                    log('TVST->Kodi (%s)' % episode.is_watched)
                    command = '{"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.SetEpisodeDetails", "params": {"episodeid" : %s, "playcount": %s}}' % (result['result']['episodes'][i]['episodeid'], episode.is_watched)
                    result2 = json.loads(xbmc.executeJSONRPC(command))
            if ((i+1) % 8) == 0:
                    xbmc.sleep(60000)
        busy = False
                
    def createSchedules(self,forceUpdate = False):
        log("update timers")
        self.lock = True
        self.schedules = []
                                   
        if(self.auto_sync == 'true'):
            log("Creating timer for Auto Sync");
            aSchedule = CronSchedule()
            aSchedule.name = __language__(33001)
            aSchedule.command = 'Sync'
            aSchedule.expression = self.checkTimer()
            aSchedule.next_run = self.calcNextRun(aSchedule.expression,self.last_run)
            self.schedules.append(aSchedule)
        self.lock = False
        self.showNotify(not forceUpdate)
        
    def checkTimer(self):
        result = ''
        if(self.advanced_timer == 'true'):
            result = self.advanced
        else:
            result = '0 */' + str(self.timer_amounts[self.timer_value]) + ' * * *'
        return result
    
    def calcNextRun(self,cronExp,startTime):
        cron = croniter(cronExp,startTime)
        nextRun = cron.get_next(float)
        return nextRun

    def showNotify(self,displayToScreen = True):
        log("showNotify")
        next_run_time = CronSchedule()
        for cronJob in self.schedules:
            if(cronJob.next_run < next_run_time.next_run or next_run_time.next_run == 0):
                next_run_time = cronJob
        inWords = self.nextRunCountdown(next_run_time.next_run)
        if(next_run_time.next_run > time.time() and self.notifications == 'true' and displayToScreen == True):
            notif("%s %s - %s" % (__language__(33001), next_run_time.name, inWords), time=2500)
        return inWords    

    def nextRunCountdown(self,nextRun):
        cronDiff = nextRun - time.time()
        if cronDiff < 0:
            return ""
        hours = int((cronDiff / 60) / 60)
        minutes = int(round(cronDiff / 60.0 - hours * 60))
        if minutes == 0:
            minutes = 1
        result = str(hours) + " h " + str(minutes) + " m"
        if hours == 0:
            result = str(minutes) + " m"
        elif hours > 36:
            result = datetime.fromtimestamp(nextRun).strftime('%m/%d %I:%M%p')
        elif hours > 24:
            days = int(hours / 24)
            hours = hours - days * 24
            result = str(days) + " d " + str(hours) + " h " + str(minutes) + " m"
        return result
        
    def readLastRun(self):
        if(self.last_run == 0):
            self.last_run = float(self.last_run_setting)
        log("Read last_run=%s" % self.last_run_setting)

    def writeLastRun(self):
        __addon__.setSetting('last_run', str(self.last_run))
        log("Set last_run=%s" % self.last_run)

    def scanRunning(self):
        if(xbmc.getCondVisibility('Library.IsScanningVideo') or xbmc.getCondVisibility('Library.IsScanningMusic')):
            return True            
        else:
            return False
            
    def databaseUpdated(self,database):
        self.writeLastRun()
            
    def _networkUp(self):
        log("Starting network check")
        try:
            response = urllib2.urlopen('http://www.google.com',timeout=1)
            return True
        except:
            pass
        return False
        
class CronSchedule:
    expression = ''
    name = 'library'
    timer_type = 'xbmc'
    command = 'Sync'
    next_run = 0
    on_delay = False

    def cleanLibrarySchedule(self,selectedIndex):
        if(selectedIndex == 1):
            return "* * *"
        elif (selectedIndex == 2):
            return "* * 0"
        else:
            return "1 * *"

class Player(xbmc.Player):

    def __init__ (self):
        xbmc.Player.__init__(self)
        log('Player - init')
        self.token = __addon__.getSetting('token')
        self.notifications = __addon__.getSetting('notifications')
        if self.token is '':
            log(__language__(32901))
            notif(__language__(32901), time=2500)
            return
        self.user = self._loginTVST()
        if not self.user.is_authenticated:
            return
        self._monitor = Monitor(action = self._reset)
        log('Player - monitor')
        AutoUpdater().runProgram()
        log("Auto Update Service starting...")
        
    def _reset(self):
        self.__init__()

    def _loginTVST(self):
        log('_loginTVST')
        user = GetUserInformations(self.token)
        if user.is_authenticated:
            if self.notifications:
                notif('%s %s' % (__language__(32902), user.username), time=2500)
        else:
            notif(__language__(32903), time=2500)
        return user

def formatNumber(number):
    if len(number) < 2:
         number = '0%s' % number
    return number
	 
def formatName(filename):
    filename = filename.strip()
    filename = filename.replace(' ', '.')
    return filename	 
    
def notif(msg, time=5000):
    notif_msg = "%s, %s, %i, %s" % (__scriptname__, msg, time, __icon__)
    xbmc.executebuiltin("XBMC.Notification(%s)" % notif_msg.encode('utf-8'))

def log(msg):
    xbmc.log("### [%s] - %s" % (__scriptname__, msg.encode('utf-8'), ),
            level=xbmc.LOGDEBUG) #100 #xbmc.LOGDEBUG

def _is_excluded(filename):
    log("_is_excluded(): Check if '%s' is a URL." % filename)
    excluded_protocols = ["pvr://", "http://", "https://"]
    return any(protocol in filename for protocol in excluded_protocols)

if ( __name__ == "__main__" ):
    Player()
    log("[%s] - Version: %s Started" % (__scriptname__, __version__))

    while not xbmc.abortRequested:
        xbmc.sleep(100)

    log("sys.exit(0)")
    sys.exit(0)

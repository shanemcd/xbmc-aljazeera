#!/usr/bin/env python
# Copyright 2011 Jonathan Beluch. 
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from resources.lib.xbmcswift.plugin import XBMCSwiftPlugin
from resources.lib.xbmcswift.common import download_page
from resources.lib.xbmcswift.getflashvideo import get_flashvideo_url, YouTube
from BeautifulSoup import BeautifulSoup as BS, SoupStrainer as SS
from urllib import urlencode
from urlparse import urljoin
import re
try:
    import json
except ImportError:
    import simplejson as json
import xbmc, xbmcgui

__plugin__ = 'AlJazeera'
__plugin_id__ = 'plugin.video.aljazeera'

plugin = XBMCSwiftPlugin(__plugin__, __plugin_id__)

BASE_URL = 'http://english.aljazeera.net'
def full_url(path):
    return urljoin(BASE_URL, path)

def parse_queryvideo_args(s):
    '''Parses the string "QueryVideos(13,'africanews',1,1)" and returns
    ('13', 'africanews', '1', '1')'''
    p = re.compile('QueryVideos\((.+?)\)')
    m = p.search(s)
    if not m:
        return None
    count, list_id, start_index, method = m.group(1).split(',')
    return count, list_id.strip("'"), start_index, method

def parse_video(video):
    '''Returns a dict of information for a given json video object.'''
    info = {
        'title': video['title']['$t'],
        'summary': video['media$group']['media$description']['$t'],
        'videoid': video['media$group']['yt$videoid']['$t'],
    }

    # There are multiple images returned, default to high quality
    images = video['media$group']['media$thumbnail']
    for image in images:
        if image['yt$name'] == u'hqdefault':
            info['thumbnail'] = image['url']

    # Make a datetime
    #info['published'] = video['published']['$t']
    return info

def get_videos(count, list_id, start_index):
    '''Returns a tuple of (videos, total_videos) where videos is a list of 
    dicts containing video information and total_videos is the toal number
    of videos available for the given list_id. The number of videos returned
    is specified by the given count.
    
    This function queris the gdata youtube API. The AlJazeera website uses the
    same API on the client side via javascript.'''
    params = {
        'v': '2',
        'author': 'AlJazeeraEnglish',
        'alt': 'json',
        'max-results': count,
        'start-index': start_index,
        'prettyprint': 'true',
        'orderby': 'updated',
    }
    url_ptn = 'http://gdata.youtube.com/feeds/api/videos/-/%s?%s'
    url = url_ptn % (list_id, urlencode(params))
    src = download_page(url)
    resp = json.loads(src)
    videos  = resp['feed']['entry']
    video_infos = map(parse_video, videos)
    total_results = resp['feed']['openSearch$totalResults']['$t']
    return video_infos, total_results


#### Plugin Views ####

# Default View
@plugin.route('/', default=True)
def show_homepage():
    items = [
        # Watch Live
        {'label': plugin.get_string(30100), 'url': plugin.url_for('watch_live')},
        # News Clips
        {'label': plugin.get_string(30101), 'url': plugin.url_for('show_clip_categories')},
        # Programs
        {'label': plugin.get_string(30102), 'url': plugin.url_for('show_program_categories')},
    ]
    return plugin.add_items(items)

@plugin.route('/live/')
def watch_live():
    rtmpurl = 'rtmp://aljazeeraflashlivefs.fplive.net:1935/aljazeeraflashlive-live/aljazeera_english_1 live=true'
    li = xbmcgui.ListItem('AlJazeera Live')
    xbmc.Player(xbmc.PLAYER_CORE_DVDPLAYER).play(rtmpurl, li)
    # Return an empty list so we can test with plugin.crawl() and plugin.interactive()
    return []

def only_clip_categories(s):
    return s.find("SelectProgInfo('Selected');") > -1

def only_program_categories(s):
    return not only_clip_categories(s)

@plugin.route('/categories/clips/', onclick_func=only_clip_categories, name='show_clip_categories', clips=True)
@plugin.route('/categories/programs/', name='show_program_categories', onclick_func=only_program_categories)
def show_categories3(onclick_func, clips=False):
    '''Shows categories available for either Clips or Programs on the aljazeera video page.'''
    url = full_url('video')
    src = download_page(url)
    # Fix shitty HTML so BeautifulSoup doesn't break
    src = src.replace('id"adSpacer"', 'id="adSpacer"')
    html = BS(src)

    tds = html.findAll('td', {
        'id': re.compile('^mItem_'),
        'onclick': onclick_func,
    })

    items = []

    # The first link for the 'Clips' section links directly to a video so we must handle it differently.
    if clips:
        videos, total_results = get_videos('1', 'vod', '1')
        video = videos[0]
        items.append({
            'label': video['title'],
            'thumbnail': video['thumbnail'],
            'info': {'plot': video['summary'], },
            'url': plugin.url_for('watch_video', videoid=video['videoid']),
            'is_folder': False,
            'is_playable': True,
        })
        tds = tds[1:]

    for td in tds: 
        count, list_id, start_index, method = parse_queryvideo_args(td['onclick'])
        items.append({
            'label': td.string,
            'url': plugin.url_for('show_videos', count=count, list_id=list_id, start_index=start_index),
        })

    return plugin.add_items(items)

@plugin.route('/videos/<list_id>/<start_index>/<count>/')
def show_videos(list_id, start_index, count):
    '''List videos available for a given category. Only 13 videos are displayed at a time.
    If there are older or newwer videos, appropriate list items will be placed at the top of
    the list.'''
    videos, total_results = get_videos(count, list_id, start_index)
    items = [{
        'label': video['title'],
        'thumbnail': video['thumbnail'],
        'info': {'plot': video['summary'], },
        'url': plugin.url_for('watch_video', videoid=video['videoid']),
        'is_folder': False,
        'is_playable': True,
    } for video in videos]

    # MOAR VIDEOS
    # Add '> Older' and '< Newer' list items if the list spans more than 1 page (e.g. > 13 videos)
    if int(start_index) + int(count) < int(total_results):
        items.insert(0, {
            # Older videos
            'label': '> %s' % plugin.get_string(30200),
            'url': plugin.url_for('show_videos', count=count, list_id=list_id, start_index=str(int(start_index) + int(count))),
        })
    if int(start_index) > 1:
        items.insert(0, {
            # Newer videos
            'label': '< %s' % plugin.get_string(30201),
            'url': plugin.url_for('show_videos', count=count, list_id=list_id, start_index=str(int(start_index) - int(count))),
        })

    return plugin.add_items(items)

@plugin.route('/watch/<videoid>/')
def watch_video(videoid):
    url = YouTube.get_flashvideo_url(videoid=videoid)
    return plugin.set_resolved_url(url)

if __name__ == '__main__': 
    plugin.run()

    # for testing
    #plugin.interactive()
    #plugin.crawl()






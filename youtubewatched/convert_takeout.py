import itertools
import logging
import os
import re
import unicodedata

from datetime import datetime
from os.path import join
from typing import Union

from bs4 import BeautifulSoup as BSoup

from youtubewatched.utils.gen import (
    timestamp_is_unique_in_list, remove_timestamps_from_one_list_from_another)

logger = logging.getLogger(__name__)

"""
In addition to seemingly only returning an oddly even number of records 
(20300 the first time, 18300 the second), Takeout also seems to only return 
from no farther back than 2014. (update: seems to go farther for accounts with 
less videos watched)
When compared to the list you'd get from scraping your YouTube history web page 
directly (which seems to go back to the very start of your account), 
it's missing a number of videos from every year, even the current. The 
current year is only missing 15, but the number increases the further back you 
go, ending up in hundreds.
Inversely, Takeout has 1352 records which are not present on Youtube's 
history page. Only 9 of them were videos that were still up when last checked, 
however. Most or all of them have their urls listed as their titles in Takeout.

There's also 3 videos which have titles, but not channel info. They're no 
longer up on YouTube.

-----

Turns out the reason for BS not seeing all/any divs was an extra,
out-of-place tag - <div class="mdl-grid"> (right after <body>) instead of 
indentation and newlines. Thought Beautiful Soup was supposed to handle that 
just fine, but maybe not or not in all cases. 

Update:
Perhaps the above tag is not out of place, but is paired with a </div> at the 
very end of the file. Its presence still doesn't make sense 
as divs with the same class also wrap every video entry individually.
"""

watch_url_re = re.compile(r'watch\?v=')
channel_url_re = re.compile(r'youtube\.com/channel')
dt_re = re.compile(
    r'[a-zA-Z]{3} \d{1,2}, \d{4}, \d{1,2}:\d{1,2}:\d{1,2} [APM]{2} ')


def extract_video_id_from_url(url):
    video_id = url[url.find('=') + 1:]
    id_end = video_id.find('&t=')
    if id_end > 0:
        video_id = video_id[:id_end]

    return video_id


def get_watch_history_files(takeout_path: str = '.'):
    """
    Locates watch-history.html files in a given path.

    Only works if the provided path points to any of the following:
     - a single file itself, ex.
     <root dir>/Takeout/YouTube/history/watch-history.html
     - a directory with watch-history file(s)
     - a directory with directories of extracted Takeout archives

    The search will become confined to one of these types after the first
    match, i.e. if a watch-history file is found in the directory that was
    passed, it'll continue looking for those within the same directory, but not
    in Takeout directories.
    Processing will be slightly faster if the files are ordered chronologically.
    """
    if os.path.isfile(takeout_path):
        if 'watch-history' in takeout_path:
            return [takeout_path]
        else:
            return

    dir_contents = os.listdir(takeout_path)
    watch_histories = []
    for path in dir_contents:
        if path.startswith('watch-history') and path.endswith('.html'):
            watch_histories.append(os.path.join(takeout_path, path))

    if watch_histories:
        return watch_histories  # assumes a directory with a single
        # watch-history file or with multiple ones (with something appended to
        # the end of their file names)
    for path in dir_contents:
        if path.startswith('takeout-2') and path[-5:-3] == 'Z-':
            full_path = os.path.join(takeout_path, path, 'Takeout', 'YouTube',
                                     'history', 'watch-history.html')
            if os.path.exists(full_path):
                watch_histories.append(os.path.join(takeout_path, full_path))
            else:
                logger.warning(f'Expected watch-history.html in {path}, '
                               f'found none')

    return watch_histories


fluff = [  # the order should not be changed
    ('<div class="mdl-grid">', ''),
    ('<div class="outer-cell mdl-cell mdl-cell--12-col '
     'mdl-shadow--2dp">', ''),
    ('<div class="header-cell mdl-cell mdl-cell--12-col">'
     '<p class="mdl-typography--title">YouTube<br></p></div>', ''),
    ('"content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1"',
     '"awesome_class"'),
    (('<div class="content-cell mdl-cell mdl-cell--6-col '
      'mdl-typography--body-1 mdl-typography--text-right"></div><div '
      'class="content-cell mdl-cell mdl-cell--12-col mdl-typography'
      '--caption"><b>Products:</b><br>&emsp;YouTube'
      '<br></div></div></div>'), ''),
    ('<', '\n<'),
    ('>', '>\n')
]
done_ = '<span id="Done">'

removed_string = 'Watched a video that has been removed'
story_string = 'Watched story'


def get_all_records(takeout_path: str = '.',
                    dump_json_to_dir: str = None, prune_html=False,
                    verbose=True) -> Union[dict, bool]:
    """
    Accumulates records from all found watch-history.html files and returns
    them in a dict.

    :param takeout_path: directory containing Takeout directories or
    watch-history.html files, or a path to one of those files directly
    :param dump_json_to_dir: saves the dict with accumulated records to a
    json file
    :param prune_html: prunes HTML that doesn't allow or slows down the
    processing of files with Beautiful Soup
    :param verbose:
    :return:
    """

    watch_files = get_watch_history_files(takeout_path)
    if not watch_files:
        logger.warning('Found no watch-history files.')
        return {}

    occ_dict = {'videos': {'unknown': {'timestamps': []}},
                'failed_entries': [],
                'failed_files': []}

    failed_entries = 0

    def add_failed_parse_entry_to_list(div_text):
        nonlocal failed_entries
        occ_dict['failed_entries'].append(div_text)
        failed_entries += 1

    watch_files_amount = len(watch_files)
    for ind, watch_file_path in enumerate(watch_files):
        yield ind, watch_files_amount
        try:
            with open(watch_file_path, 'r', encoding='utf-8') as watch_file:
                content = unicodedata.normalize('NFKD', watch_file.read())
                original_content = content
        except UnicodeDecodeError:
            occ_dict['failed_files'].append(watch_file_path)
            logger.error(f'Failed to decode {watch_file_path}')
            continue
        if not content.startswith(done_):  # cleans out all the junk for faster
            # BSoup parsing, in addition to fixing an out-of-place-tag which
            # stops BSoup from parsing more than a couple dozen records
            content = content[content.find('<body>')+6:
                              content.find('</body>')-6]
            for piece in fluff:
                content = content.replace(piece[0], piece[1])
            content = done_ + '\n' + content
        if content != original_content and prune_html:
            with open(watch_file_path, 'w') as new_file:
                new_file.write(content)
            logger.info('Rewrote', watch_file_path, '(trimmed junk HTML).')

        soup = BSoup(content, 'lxml')
        divs = soup.find_all('div', class_='awesome_class')

        if len(divs) == 0:
            occ_dict['failed_files'].append(watch_file_path)
            logger.error(f'Could not find any records in {watch_file_path}.'
                         f'\nThe file is either corrupt or its format is '
                         f'different from the expected.')
            continue
        for div in divs:
            default_values = {'timestamps': []}
            video_id = 'unknown'
            all_text = div.get_text().strip()
            watched_at = all_text.splitlines()[-1].strip()

            if (all_text.startswith(removed_string) or
                    all_text.startswith(story_string)):
                pass
            elif all_text.startswith('Visited YouTube Music'):
                video_id = 'youtube_music'
            else:
                url = div.find(href=watch_url_re)
                if url is None:
                    add_failed_parse_entry_to_list(all_text)
                    continue
                video_id = extract_video_id_from_url(url['href'])
                video_title = url.get_text(strip=True)
                if (url['href'] != video_title and 
                        video_title != 'Deleted video'):
                    # Some videos have the url as the title.
                    # They're usually not available through YT or its API
                    default_values['title'] = video_title
                    try:
                        channel = div.find(href=channel_url_re)
                        channel_url = channel['href']
                        channel_id = channel_url[channel_url.rfind('/') + 1:]
                        channel_title = channel.get_text(strip=True)
                        default_values['channel_id'] = channel_id
                        default_values['channel_title'] = channel_title
                    except TypeError:
                        pass

            try:
                watched_at = datetime.strptime(
                    watched_at[:watched_at.rfind(' ')],
                    '%b %d, %Y, %I:%M:%S %p')
            except ValueError:
                add_failed_parse_entry_to_list(all_text)
                continue

            occ_dict['videos'].setdefault(video_id, default_values)
            default_keys = list(default_values.keys())
            default_keys.remove('timestamps')
            for key in default_keys:
                # checks if the newer record has some data that the one
                # that's already set doesn't. Sets it if so
                if not occ_dict['videos'][video_id].get(key, None):
                    occ_dict['videos'][video_id][key] = default_values[key]

            cur_timestamps = occ_dict['videos'][video_id]['timestamps']
            timestamp_is_unique_in_list(watched_at, cur_timestamps, insert=True)

    all_known_timestamps_ids = list(occ_dict['videos'].keys())
    all_known_timestamps_ids.remove('unknown')
    all_known_timestamps_lists = [i for i in
                                  [occ_dict['videos'][v_id]['timestamps']
                                   for v_id in all_known_timestamps_ids]]
    all_known_timestamps = list(itertools.chain.from_iterable(
        all_known_timestamps_lists))
    unk_timestamps = occ_dict['videos']['unknown']['timestamps']
    unk_timestamps = sorted(
        list(set(unk_timestamps).difference(all_known_timestamps)))
    occ_dict['videos']['unknown']['timestamps'] = unk_timestamps
    remove_timestamps_from_one_list_from_another(all_known_timestamps,
                                                 unk_timestamps)

    total_timestamps = len(all_known_timestamps + unk_timestamps)
    total_videos = len(occ_dict["videos"]) - 1  # minus one for 'unknown' key

    occ_dict['total_timestamps'] = total_timestamps
    occ_dict['total_videos'] = total_videos

    if occ_dict['failed_entries']:
        logger.error(f'''Could not parse {failed_entries} entries from 
        Takeout. ''')

    if verbose:
        logger.info(f'''
        Total videos watched/opened: {total_timestamps})
        Total unknown videos: {len(unk_timestamps)})
        Unique videos with ids: {total_videos}''')
    if dump_json_to_dir:
        import json
        with open(
                join(dump_json_to_dir, 'parsed_watch_history.json'),
                'w') as all_records_file:
            json.dump(occ_dict['videos'], all_records_file, indent=4,
                      default=lambda o: str(o))  # for dt objects
            if failed_entries or occ_dict['failed_files']:
                fails = {'failed_files': occ_dict['failed_files'],
                         'failed_entries': occ_dict['failed_entries']}
                parse_fails_path = join(dump_json_to_dir, 'parse_fails.json')
                with open(parse_fails_path, 'w') as parse_fails_file:
                    json.dump(fails, parse_fails_file, indent=4)
                    logger.warning(f'Dumped failed parse data '
                                   f'in {parse_fails_path}')
            if verbose:
                logger.info(f'Dumped JSON to {dump_json_to_dir}')

    yield occ_dict

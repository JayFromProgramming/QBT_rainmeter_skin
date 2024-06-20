import logging
import os
import pathlib

import humanize

from datetime import datetime
from pytz import timezone

_intervals = (
    ('w', 604800),
    ('d', 86400),
    ('h', 3600),
    ('m', 60),
    ('s', 1),
)

_barColors = {
    'Error': "ff0000ff",
    'Deleted': "ff0000ff",
    'Uploading': "007bffff",
    'PausedUP': "00ff00ff",
    'QueuedUP': "007bffff",
    'StalledUP': "b0b0b0ff",
    'CheckingUP': "007bffff",
    'ForcedUP': "ff0000ff",
    'Allocating': "b0b0b0ff",
    'Downloading': "00ff00ff",
    'MetaDL': "007bffff",
    'PausedDL': "b0b0b0ff",
    'QueuedDL': "b0b0b0ff",
    'StalledDL': "b0b0b0ff",
    'CheckingDL': "ff0000ff",
    'ForcedDL': "ff0000ff",
    'CheckingResumeData': "b0b0b0ff",
    'Moving': "ff0000ff",
    'Unknown': "ff0000ff"
}

_show_seeders = [
    "Allocating",
    "Downloading",
    "MetaDL",
    "PausedDL",
    "QueuedDL",
    "StalledDL",
    "CheckingDL",
    "ForcedDL",
    "CheckingResumeData",
    "Unknown"
]


def _display_time(seconds, granularity=2):
    result = []

    for name, count in _intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{}{}".format(value, name))
    return ' '.join(result[:granularity])


def torrent_format(tr_dict):
    rm_values = {}
    for i in range(4):
        rm_values[f'TorrentName{i}'] = {'Text': tr_dict[i]['name']}
        rm_values[f'TorrentName{i}']['ToolTipText'] = tr_dict[i]['name']
        temp_path = os.path.abspath(tr_dict[i]['content_path'].replace("/mnt/qnap/Shared", r"\\172.17.0.1\Shared"))
        if os.path.isdir(temp_path):
            save_path = temp_path
        else:
            save_path = os.path.dirname(temp_path)
        rm_values[f'TorrentName{i}']['LeftMouseDoubleClickAction'] = f"\"\"[\"explorer.exe\" \"{save_path}\"]\"\""
        rm_values[f'TorrentStatus{i}'] = {'Text': tr_dict[i]['state'][0].upper() + tr_dict[i]['state'][1:]}
        rm_values[f'TorrentDSpeed{i}'] = {'Text': "Down speed: " + humanize.naturalsize(tr_dict[i]['dlspeed']) + "/s"}
        if rm_values[f'TorrentStatus{i}']['Text'] in _show_seeders:
            rm_values[f'TorrentSeeds{i}'] = {'Text': f"Seeds: {tr_dict[i]['num_complete']}({tr_dict[i]['num_seeds']})"}
        else:
            rm_values[f'TorrentSeeds{i}'] = {'Text': \
                f"Leechs: {tr_dict[i]['num_incomplete']}({tr_dict[i]['num_leechs']})"}
        rm_values[f'TorrentETA{i}'] = {'Text': "ETA: " + _display_time(tr_dict[i]['eta'])}
        rm_values[f'TorrentPercentage{i}'] = {'Text': f"{tr_dict[i]['progress'] * 100:.1f}%"}
        rm_values[f'TorrentProgress{i}'] = {'Text': \
              humanize.naturalsize(tr_dict[i]['downloaded']) + "/" +\
              humanize.naturalsize(tr_dict[i]['downloaded'] + tr_dict[i]['amount_left'])}
        rm_values[f'TorrentProgressBar{i}'] = {'BarColor': _barColors[rm_values[f'TorrentStatus{i}']['Text']]}
        rm_values[f'TorrentUSpeed{i}'] = {'Text': "Up speed: " + humanize.naturalsize(tr_dict[i]['upspeed']) + "/s"}
        rm_values[f'TorrentAddedOn{i}'] = {'Text': humanize.naturaltime(
            datetime.fromtimestamp(tr_dict[i]['added_on'], tz=timezone("US/Eastern")).replace(tzinfo=None)
        )}
        rm_values[f'TorrentRatio{i}'] = {'Text': f"Ratio: {tr_dict[i]['ratio']:.2f}"}
    logging.debug(f"First torrent: {rm_values['TorrentName0']}")
    return rm_values


def no_torrent_template():
    rm_values = {}
    for i in range(4):
        rm_values[f'TorrentName{i}'] = {'Text': "No Info", 'ToolTipText': "No Info", 'LeftMouseDoubleClickAction': ""}
        rm_values[f'TorrentStatus{i}'] = {'Text': "Unknown"}
        rm_values[f'TorrentDSpeed{i}'] = {'Text': "Down speed: 0B/s"}
        rm_values[f'TorrentSeeds{i}'] = {'Text': "Seeds: 0(0)"}
        rm_values[f'TorrentETA{i}'] = {'Text': "ETA: ∞"}
        rm_values[f'TorrentPercentage{i}'] = {'Text': "0%"}
        rm_values[f'TorrentProgress{i}'] = {'Text': "0B/0B"}
        rm_values[f'TorrentProgressBar{i}'] = {'BarColor': _barColors['Unknown']}
        rm_values[f'TorrentUSpeed{i}'] = {'Text': "Up speed: 0B/s"}
        rm_values[f'TorrentAddedOn{i}'] = {'Text': "Never"}
        rm_values[f'TorrentRatio{i}'] = {'Text': "Ratio: 0.00"}
    return rm_values

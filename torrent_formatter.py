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
        rm_values[f'TorrentStatus{i}'] = {'Text': tr_dict[i]['state'].capitalize()}
        rm_values[f'TorrentDSpeed{i}'] = {'Text': humanize.naturalsize(tr_dict[i]['dlspeed']) + "/s"}
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
        rm_values[f'TorrentUSpeed{i}'] = {'Text': humanize.naturalsize(tr_dict[i]['upspeed']) + "/s"}
        rm_values[f'TorrentAddedOn{i}'] = {'Text': humanize.naturaltime(
            datetime.fromtimestamp(tr_dict[i]['added_on'], tz=timezone("US/Eastern")).replace(tzinfo=None)
        )}
        rm_values[f'TorrentRatio{i}'] = {'Text': f"{tr_dict[i]['ratio']:.2f}"}
    return rm_values

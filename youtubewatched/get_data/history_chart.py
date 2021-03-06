import sqlite3

import dash_table
import numpy as np
import pandas as pd

from youtubewatched.get_data.misc import generic_table_settings

pd.set_option('display.max_columns', 400)
pd.set_option('display.width', 400)


def retrieve_watch_data(conn: sqlite3.Connection,
                        date_period: str) -> pd.DataFrame:
    """Retrieves timestamps for all videos opened from the database, groups
    them by a specified Pandas offset alias for a time series frequency"""
    query = 'SELECT watched_at FROM videos_timestamps'
    df = pd.read_sql(query, conn, index_col='watched_at')
    if date_period in ('Y', 'M'):
        date_period += 'S'

    df = df.groupby(pd.Grouper(freq=date_period))
    df = df.size().reset_index(name='times')

    return df


gen_query = """SELECT v.title AS Title, c.title AS Channel,
    count(v.title) AS Views FROM 
    videos_timestamps vt JOIN videos v ON v.id = vt.video_id 
    JOIN channels c ON v.channel_id = c.id
    WHERE vt.watched_at LIKE ?
    GROUP BY v.id;"""
summary_channels_query = """SELECT c.title AS Channel,
    count(c.title) AS Views FROM 
    videos_timestamps vt JOIN videos v ON v.id = vt.video_id 
    JOIN channels c ON v.channel_id = c.id
    WHERE vt.watched_at LIKE ?
    GROUP BY c.id
    ORDER BY Views DESC;"""
tags_query = f"""SELECT t.tag AS Tag, count(t.tag) AS Count FROM
    videos_timestamps vt JOIN videos_tags vtgs ON vtgs.video_id = vt.video_id 
    JOIN tags t ON vtgs.tag_id = t.id
    WHERE vt.watched_at LIKE ?
    GROUP BY t.tag
    ORDER BY Count DESC
    LIMIT 10;"""
topics_query = f"""SELECT t.topic AS Topic, count(t.topic) AS Count FROM
    videos_timestamps vt JOIN videos_topics v_topics
    ON vt.video_id = v_topics.video_id
    JOIN topics t ON v_topics.topic_id = t.id 
    WHERE vt.watched_at LIKE ?
    --AND t.topic NOT LIKE '%(parent topic)'
    GROUP BY t.topic
    ORDER BY Count DESC
    LIMIT 10;"""

style_cell_cond_main = [
    {'if': {'column_id': 'Title'}, 'textAlign': 'left',
     'width': '600px', 'maxWidth': '600px', 'minWidth': '600px'
     },
    {'if': {'column_id': 'Channel'}, 'textAlign': 'left',
     'width': '600px', 'maxWidth': '600px', 'minWidth': '600px'
     },
    {'if': {'column_id': 'Channel/video'}, 'textAlign': 'left',
     'width': '600px', 'maxWidth': '600px', 'minWidth': '600px'
     },
    {'if': {'column_id': 'Views'},
     'width': '50px', 'maxWidth': '50px', 'minWidth': '50px'
     }
]
style_cell_cond_aux = [
    {'if': {'column_id': 'Tag'}, 'textAlign': 'left',
     'width': '200px', 'maxWidth': '200px', 'minWidth': '200px'
     },
    {'if': {'column_id': 'Topic'}, 'textAlign': 'left',
     'width': '200px', 'maxWidth': '200px', 'minWidth': '200px'
     },
    {'if': {'column_id': 'Count'},
     'width': '50px', 'maxWidth': '50px', 'minWidth': '50px'
     }]


def make_summary_tables_for_time_period(conn: sqlite3.Connection, date: str):
    """
    Called when a user clicks on a point on the history chart. Constructs
    a few tables with basic stats for that point in time.
    """
    params = (date + '%',)

    tags = pd.read_sql(tags_query, conn, params=params)
    tags['Tag'] = tags['Tag'].str.lower()
    tags = tags.groupby(by='Tag').agg(list)
    tags['Count'] = [sum(i) if not isinstance(i, int) else i
                     for i in tags['Count']]

    tags = tags.sort_values(by='Count', ascending=False)
    tags = tags.reset_index()
    topics = pd.read_sql(topics_query, conn, params=params)
    if len(date) > 7:
        summary = pd.read_sql(gen_query, conn, params=params)
        channels = summary.drop('Title', axis=1)
        channels = channels.groupby(by='Channel').agg(np.sum)

        channels = channels.sort_values(by='Views', ascending=False)
        summary = summary.drop('Views', axis=1)
        summary = summary[summary['Title'] != 'unknown']
        channels = channels.reset_index()
        if len(date) == 13:
            date = date + ':00'
        main_table_cols = [
            {'name': ['Channel/video'], 'id': 'Channel'},
            {'name': ['Views'], 'id': 'Views'}
        ]
        channel_rows = channels.to_dict('rows')
        summary_rows = summary.to_dict('rows')
        table_rows = []
        channel_rows_indexes = []
        for dct in channel_rows:
            table_rows.append(dct)
            channel_rows_indexes.append(len(table_rows)-1)
            for vid_dict in summary_rows:
                if vid_dict['Channel'] == dct['Channel']:
                    row = {'Channel': vid_dict['Title']}
                    table_rows.append(row)
        style_cell_cond_main.extend(
            [{'if': {'row_index': i}, 'backgroundColor': '#A1C935'} for i
             in channel_rows_indexes])
        # resetting cell color back to white for cells that were set to green by
        # previous daily/hourly queries
        style_cell_cond_main.extend(
            [{'if': {'row_index': i}, 'backgroundColor': 'white'} for i
             in range(len(table_rows)) if i not in channel_rows_indexes])
    else:
        channels = pd.read_sql(summary_channels_query, conn, params=params)

        min_views = 5 if len(date) == 4 else 2  # channels with views below
        # this amount are combined into one entry for yearly/monthly summaries

        truncated_views = channels[channels['Views'] < min_views]
        channels = channels[channels['Views'] >= min_views]
        one_views_sum = truncated_views['Views'].sum()
        channels.iloc[-1] = [f'Channels with under {min_views} views',
                             one_views_sum]
        column_names = ['Channel', 'Views']
        main_table_cols = [{'name': [n], 'id': n}
                           for n in column_names]
        table_rows = channels.to_dict('rows')
        # below .extend necessary due to green colored cells remaining that way
        # the entire time after calling summary on a day/hour value, even when
        # calling it on year/month value afterwards
        style_cell_cond_main.extend(
            [{'if': {'row_index': i}, 'backgroundColor': 'white'} for i
             in range(len(table_rows))])

    views = (date + ' (total views: ' + str(channels.Views.sum()) + ')')
    for col_entry in main_table_cols:
        col_entry['name'].insert(0, views)
    tables_margin = {'margin': '5'}
    main_table = dash_table.DataTable(
        columns=main_table_cols,
        data=table_rows, id='channels-table',
        style_table={'maxHeight': '370', 'maxWidth': '800', **tables_margin},
        n_fixed_rows=2,
        style_cell_conditional=style_cell_cond_main,
        **generic_table_settings)

    tags_cols = [{'name': ['Top 10 tags', n], 'id': n} for n in tags.columns]
    tags_rows = tags.to_dict('rows')
    tags_table = dash_table.DataTable(
        columns=tags_cols,
        data=tags_rows, id='tags-table',
        style_table={'maxHeight': '377', 'maxWidth': '300', **tables_margin},
        n_fixed_rows=1,
        style_cell_conditional=style_cell_cond_aux,
        **generic_table_settings)

    topics_cols = [{'name': ['Top 10 topics', n], 'id': n}
                   for n in topics.columns]
    topics_rows = topics.to_dict('rows')
    topics_table = dash_table.DataTable(
        columns=topics_cols,
        data=topics_rows, id='topics-table',
        style_table={'maxHeight': '377', 'maxWidth': '300', **tables_margin},
        n_fixed_rows=1,
        style_cell_conditional=style_cell_cond_aux,
        **generic_table_settings)

    return main_table, tags_table, topics_table

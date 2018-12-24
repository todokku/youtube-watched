video_keys_and_columns = ('id', 'publishedAt',
                          'channelId', 'title',
                          'description',
                          'channelTitle', 'tags',
                          'categoryId',
                          'defaultAudioLanguage',
                          'duration',
                          'viewCount',
                          'likeCount',
                          'dislikeCount',
                          'commentCount',
                          'relevantTopicIds')

video_parts_to_get = ','.join(
    list(
        {  # integers are query costs, as of Nov 2018
            "contentDetails": 2,
            "id": 0,
            "player": 0,
            "snippet": 2,
            "statistics": 2,
            "status": 2,
            "topicDetails": 2
        }.keys()))

# HikerAPI -- полный каталог эндпоинтов

OpenAPI 3.1.0 | Title: HikerAPI REST | Version: 1.7.8

Servers: `https://api.hikerapi.com` (Cloudflare) или `https://api.instagrapi.com` (без Cloudflare).

Auth: header `x-access-key: <token>`.

Total endpoints: 166

---


## /v1/highlight

- `GET /v1/user/highlights` -- req: user_id -- opt: amount,force
  - User Highlights
- `GET /v1/user/highlights/by/username` -- req: username -- opt: amount,force
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.

## /v1/media

- `GET /v1/user/clips/chunk` -- req: user_id -- opt: end_cursor
  - User Clips Chunk

## /v1/story

- `GET /v1/user/stories` -- req: user_id -- opt: amount,force
  - User Stories

## /v2/highlight

- `GET /v2/user/highlights` -- req: user_id -- opt: amount,force
  - User Highlights
- `GET /v2/user/highlights/by/username` -- req: username -- opt: amount,force
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.

## /v2/media

- `GET /v2/user/clips` -- opt: user_id,page_id,safe_int
  - User Clips

## /v2/story

- `GET /v2/user/stories` -- req: user_id -- opt: force,safe_int
  - User Stories
- `GET /v2/user/stories/by/username` -- req: username -- opt: force,safe_int
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.

## Audio

- `GET /v2/track/by/canonical/id` -- req: canonical_id -- opt: page_id
  - Track By Canonical Id
- `GET /v2/track/by/id` -- req: track_id -- opt: page_id
  - Track By Id
- `GET /v2/track/stream/by/id` -- req: track_id -- opt: page_id
  - Track Stream By Id

## Comments

- `GET /gql/comment/likers/chunk` -- opt: comment_id,media_id,end_cursor
  - Comment Likers Chunk
- `GET /v1/media/comments/chunk` -- req: id -- opt: min_id,max_id,can_support_threading
  - Get media comments (one request return 15 comments)
- `GET /v2/media/comment/offensive` -- req: media_id,comment
  - Media Check Offensive Comment
- `GET /v2/media/comments` -- req: id -- opt: can_support_threading,page_id
  - Get media comments (one request return 15 comments)
- `GET /v2/media/comments/replies` -- req: media_id,comment_id -- opt: min_id
  - Media Comments Replies

## Hashtags

- `GET /v1/hashtag/by/name` -- req: name
  - Hashtag By Name
- `GET /v1/hashtag/medias/clips/chunk` -- req: name -- opt: max_id
  - Hashtag Medias Clips Chunk
- `GET /v1/hashtag/medias/top/chunk` -- req: name -- opt: max_id
  - Hashtag Medias Top Chunk
- `GET /v1/hashtag/medias/top/recent/chunk` -- req: name -- opt: max_id
  - Hashtag Medias Top Recent Chunk
- `GET /v2/hashtag/by/name` -- req: name
  - Hashtag By Name
- `GET /v2/hashtag/medias/recent` -- req: name -- opt: page_id
  - Hashtag Medias Recent Chunk
- `GET /v2/hashtag/medias/top` -- req: name -- opt: page_id
  - Hashtag Medias Top Chunk

## Highlights

- `GET /v1/highlight/by/url` -- req: url
  - Attention! To work with /s/ links, call /v1/share/by/url first
- `GET /v2/highlight/by/id` -- req: id
  - Highlight By Id

## Location

- `GET /v1/location/by/id` -- req: id
  - Location By Id
- `GET /v1/location/guides` -- req: location_pk
  - Location Guides V1
- `GET /v1/location/medias/recent` -- req: location_pk -- opt: amount
  - Location Medias Recent V1
- `GET /v1/location/medias/recent/chunk` -- req: location_pk -- opt: max_id
  - Location Medias Recent Chunk
- `GET /v1/location/medias/top` -- req: location_pk -- opt: amount
  - Location Medias Top V1
- `GET /v1/location/medias/top/chunk` -- req: location_pk -- opt: max_id
  - Location Medias Top Chunk
- `GET /v1/location/search` -- req: lat,lng
  - Location Search

## Post Details

- `GET /gql/media/likers` -- req: media_id
  - Media Likers
- `GET /gql/media/usertags` -- opt: media_ids
  - Returns users tagged in the video. You can pass up to 10 media ids
- `GET /v1/media/by/code` -- req: code
  - Media By Code
- `GET /v1/media/by/id` -- req: id
  - Media By Id
- `GET /v1/media/by/url` -- req: url
  - Attention! Use with (https://ins...ram.com/p/CA2aJYrg6cZ/)
- `GET /v1/media/code/from/pk` -- req: pk
  - Media Code From Pk
- `GET /v1/media/comments/chunk` -- req: id -- opt: min_id,max_id,can_support_threading
  - Get media comments (one request return 15 comments)
- `GET /v1/media/insight` -- req: media_id
  - Insights Media
- `GET /v1/media/likers` -- req: id
  - Media Likers
- `GET /v1/media/oembed` -- req: url
  - Media Oembed
- `GET /v1/media/pk/from/code` -- req: code
  - Media Pk From Code
- `GET /v1/media/pk/from/url` -- req: url
  - Attention! Use with (https://ins...ram.com/p/CA2aJYrg6cZ/)
- `GET /v1/media/user` -- req: media_id
  - Media User
- `GET /v2/media/comment/offensive` -- req: media_id,comment
  - Media Check Offensive Comment
- `GET /v2/media/comments` -- req: id -- opt: can_support_threading,page_id
  - Get media comments (one request return 15 comments)
- `GET /v2/media/comments/replies` -- req: media_id,comment_id -- opt: min_id
  - Media Comments Replies
- `GET /v2/media/info/by/code` -- req: code
  - Returns 200 for found posts and 404 for unavailable or deleted posts. Other responses are not provided. Doesn't return usertags for video. Note: promoted/ad pos
- `GET /v2/media/info/by/id` -- req: id
  - Returns 200 for found posts and 404 for unavailable or deleted posts. Other responses are not provided. Doesn't return usertags for video. Note: promoted/ad pos
- `GET /v2/media/info/by/url` -- req: url
  - Returns 200 for found posts and 404 for unavailable or deleted posts. Other responses are not provided. Doesn't return usertags for video. Attention! Use with h
- `GET /v2/media/likers` -- req: id
  - Media Likers
- `GET /v2/media/template` -- req: id
  - Media Template

## Search

- `GET /gql/topsearch` -- req: query -- opt: end_cursor,flat
  - Topsearch
- `GET /v1/fbsearch/places` -- req: query -- opt: lat,lng
  - Fbsearch Places
- `GET /v1/fbsearch/topsearch` -- req: query
  - Fbsearch Topsearch
- `GET /v1/fbsearch/topsearch/hashtags` -- req: query
  - Web Search Topsearch Hashtags
- `GET /v1/search/hashtags` -- req: query
  - Search Hashtags
- `GET /v1/search/music` -- req: query
  - Search Music
- `GET /v1/search/users` -- req: query
  - It is recommended to use /v2/search/accounts as this endpoint will soon be deprecated.
- `GET /v2/fbsearch/accounts` -- req: query -- opt: page_token
  - Fbsearch Accounts
- `GET /v2/fbsearch/places` -- req: query
  - Fbsearch Places
- `GET /v2/fbsearch/reels` -- req: query -- opt: reels_max_id,rank_token
  - Fbsearch Reels
- `GET /v2/fbsearch/topsearch` -- req: query -- opt: next_max_id
  - Fbsearch Top
- `GET /v2/search/hashtags` -- req: query -- opt: page_token
  - Search Hashtags
- `GET /v2/search/music` -- req: query -- opt: next_max_id
  - Search Music
- `GET /v3/fbsearch/accounts` -- req: query -- opt: page_token
  - Fbsearch Accounts
- `GET /v3/fbsearch/places` -- req: query
  - Fbsearch Places

## Share

- `GET /v1/share/by/code` -- req: code
  - Works for stories and highlights only or use (/v1/media/by/url, /v1/story/by/url)
- `GET /v1/share/by/url` -- req: url
  - Works for stories and highlights only ig...m.com/s/aGln(link must contain /s/) or use (/v1/media/by/url, /v1/story/by/url)
- `GET /v1/share/reel/by/url` -- req: url
  - Works for reel (clips) only

## Stories

- `GET /v1/story/by/id` -- req: id
  - Story By Id
- `GET /v1/story/by/url` -- req: url
  - Attention! To work with /s/ links, call /v1/share/by/url first
- `GET /v1/story/download` -- req: id
  - Story Download
- `GET /v1/story/download/by/story/url` -- req: url
  - Download story file by story URL
- `GET /v1/story/download/by/url` -- req: url
  - Download story file by URL to file
- `GET /v2/story/by/id` -- req: id
  - Story By Id
- `GET /v2/story/by/url` -- req: url
  - Attention! To work with /s/ links, call /v1/share/by/url first

## System

- `GET /sys/balance`
  - Balance

## Top 5

- `GET /gql/user/medias` -- req: user_id -- opt: profile_grid_items_cursor,flat
  - Returns the user medias
- `GET /v2/fbsearch/topsearch` -- req: query -- opt: next_max_id
  - Fbsearch Top
- `GET /v2/media/comments` -- req: id -- opt: can_support_threading,page_id
  - Get media comments (one request return 15 comments)
- `GET /v2/user/by/username` -- req: username
  - Get user object by username (one request required). If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v2/user/stories` -- req: user_id -- opt: force,safe_int
  - User Stories

## User Profile

- `GET /a2/user` -- req: username
  - User
- `GET /g2/user/followers` -- req: user_id -- opt: page_id
  - Get a user followers (one request required)
- `GET /g2/user/following` -- req: user_id -- opt: page_id
  - Get a user following (one request required)
- `GET /gql/user/about` -- req: id
  - User About
- `GET /gql/user/clips` -- req: user_id -- opt: max_id,sort_by_views,flat
  - Returns the user's short video posts (reels).
- `GET /gql/user/followers/chunk` -- req: user_id -- opt: end_cursor,force
  - Get a user followers (one request required)
- `GET /gql/user/following/chunk` -- req: user_id -- opt: end_cursor,force
  - Get a user following (one request required)
- `GET /gql/user/medias` -- req: user_id -- opt: profile_grid_items_cursor,flat
  - Returns the user medias
- `GET /gql/user/reposts` -- req: user_id -- opt: repost_next_max_id,flat
  - Get user's reposted content
- `GET /gql/user/web_profile_info` -- req: user_id
  - Get user profile info GraphQL
- `GET /v1/user/about` -- req: id
  - We recommend switching to /gql/user/about
- `GET /v1/user/by/id` -- req: id
  - User By Id
- `GET /v1/user/by/url` -- req: url
  - Get user object by URL (one request required)
- `GET /v1/user/by/username` -- req: username
  - Get user object by username (one request required). If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v1/user/clips/chunk` -- req: user_id -- opt: end_cursor
  - User Clips Chunk
- `GET /v1/user/followers/chunk` -- req: user_id -- opt: max_id
  - Get a user followers (one request required)
- `GET /v1/user/following/chunk` -- req: user_id -- opt: max_id
  - Get a user following (one request required)
- `GET /v1/user/highlights` -- req: user_id -- opt: amount,force
  - User Highlights
- `GET /v1/user/highlights/by/username` -- req: username -- opt: amount,force
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v1/user/medias/chunk` -- req: user_id -- opt: end_cursor
  - User Medias Chunk
- `GET /v1/user/medias/pinned` -- req: user_id -- opt: amount
  - Get pinned medias
- `GET /v1/user/search/followers` -- req: user_id,query -- opt: force
  - Search Followers
- `GET /v1/user/search/following` -- req: user_id,query -- opt: force
  - Search Following
- `GET /v1/user/stories` -- req: user_id -- opt: amount,force
  - User Stories
- `GET /v1/user/stories/by/username` -- req: username -- opt: amount,force
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v1/user/tag/medias/chunk` -- req: user_id -- opt: max_id
  - Usertag Medias Chunk
- `GET /v2/user/by/id` -- req: id
  - User By Id
- `GET /v2/user/by/username` -- req: username
  - Get user object by username (one request required). If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v2/user/clips` -- opt: user_id,page_id,safe_int
  - User Clips
- `GET /v2/user/explore/businesses/by/id` -- req: user_id
  - Get recommended accounts for category by user id
- `GET /v2/user/followers` -- opt: user_id,page_id
  - Get a user followers (one request required). Prefer /g2/user/followers
- `GET /v2/user/following` -- opt: user_id,page_id
  - Get a user following (one request required). Prefer /g2/user/following
- `GET /v2/user/highlights` -- req: user_id -- opt: amount,force
  - User Highlights
- `GET /v2/user/highlights/by/username` -- req: username -- opt: amount,force
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v2/user/stories` -- req: user_id -- opt: force,safe_int
  - User Stories
- `GET /v2/user/stories/by/username` -- req: username -- opt: force,safe_int
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v2/user/suggested/profiles` -- req: user_id -- opt: expand_suggestion
  - Fetch Suggestion Details
- `GET /v2/user/tag/medias` -- opt: user_id,page_id
  - Get medias where user is tagged
- `GET /v2/userstream/by/id` -- req: id
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.
- `GET /v2/userstream/by/username` -- req: username
  - If speed is crucial, it's more efficient to use the by/id endpoint for quicker responses.

## Legacy

- `GET /gql/comment/likers` -- req: media_id -- opt: amount
  - WARNING: Preferable to use /gql/comment/likers/chunk
- `GET /gql/comments` -- req: media_id -- opt: sort_order,amount,max_requests
  - Use /v1/media/comments/chunk or /v2/media/comments instead
- `GET /gql/comments/chunk` -- req: media_id -- opt: sort_order,end_cursor
  - Use /v1/media/comments/chunk or /v2/media/comments instead
- `GET /gql/comments/threaded` -- req: media_id,comment_id -- opt: amount
  - Use /v2/media/comments/replies instead
- `GET /gql/comments/threaded/chunk` -- req: media_id,comment_id -- opt: end_cursor
  - Use /v2/media/comments/replies instead
- `GET /gql/user/by/id` -- req: id
  - User By Id
- `GET /gql/user/by/username` -- req: username
  - Get user object by username (one request required)
- `GET /gql/user/followers` -- req: user_id -- opt: amount
  - WARNING: Use /v2/user/followers. Get a user followers (one request is required for every 46 followers)
- `GET /gql/user/following` -- req: user_id -- opt: amount
  - WARNING: Use /v2/user/following. Get a user following (one request is required for every 46 following)
- `GET /gql/user/related/profiles` -- req: id
  - Prefer using v2/user/suggested/profiles as this endpoint will be completely deprecated soon
- `GET /v1/hashtag/medias/clips` -- req: name -- opt: amount
  - Use /v1/hashtag/medias/clips/chunk or /v2/hashtag/medias/clips instead
- `GET /v1/hashtag/medias/recent` -- req: name -- opt: amount
  - Hashtag Medias Recent
- `GET /v1/hashtag/medias/recent/chunk` -- req: name -- opt: max_id
  - Hashtag Medias Recent Chunk
- `GET /v1/hashtag/medias/top` -- req: name -- opt: amount
  - Use /v1/hashtag/medias/top/chunk or /v2/hashtag/medias/top instead
- `GET /v1/highlight/by/id` -- req: id
  - Highlight By Id
- `GET /v1/media/comments` -- req: id -- opt: amount
  - Get media comments (one request is required for every 20 comments)
- `GET /v1/media/download/photo` -- req: id
  - Photo Download
- `GET /v1/media/download/photo/by/url` -- req: url
  - Photo Download By Url
- `GET /v1/media/download/video` -- req: id
  - Video Download
- `GET /v1/media/download/video/by/url` -- req: url
  - Video Download By Url
- `GET /v1/user/clips` -- req: user_id -- opt: amount
  - WARNING: Use v1/user/clips/chunk. Get user clips - first page
- `GET /v1/user/followers` -- req: user_id -- opt: amount
  - WARNING: Use /v2/user/followers of /v1/user/followers/chunk. Get first page user followers
- `GET /v1/user/following` -- req: user_id -- opt: amount
  - WARNING: Use /v2/user/following or /v1/user/following/chunk. Get first page user following
- `GET /v1/user/guides` -- req: user_id
  - User Guides V1
- `GET /v1/user/medias` -- req: user_id -- opt: amount
  - WARNING: Use /v2/user/medias (better) or /v1/user/medias/chunk. Get user medias - first page
- `GET /v1/user/tag/medias` -- req: user_id -- opt: amount
  - Usertag Medias
- `GET /v1/user/videos` -- req: user_id -- opt: amount
  - Prefer using /v2/user/clips or /v2/user/medias instead
- `GET /v1/user/videos/chunk` -- req: user_id -- opt: end_cursor
  - Prefer using /v2/user/clips or /v2/user/medias instead
- `GET /v1/user/web_profile_info` -- req: username
  - WARNING: Deprecated. Instagram returns ~90% false UserNotFound since Feb 2, 2026. Use /gql/user/web_profile_info instead (accepts numeric user ID, much more rel
- `GET /v2/hashtag/medias/clips` -- req: name -- opt: page_id
  - Switch to /v2/fbsearch/reels — this endpoint will be deprecated soon. It currently returns all media types, not just reels.
- `GET /v2/media/by/code` -- req: code
  - Prefer using /v2/media/info/by/code as this endpoint will be completely deprecated soon
- `GET /v2/media/by/id` -- req: id
  - Prefer using /v2/media/info/by/id as this endpoint will be completely deprecated soon
- `GET /v2/media/by/url` -- req: url
  - Prefer using /v2/media/info/by/url as this endpoint will be completely deprecated soon
- `GET /v2/search/accounts` -- req: query -- opt: page_token
  - Switch to /v2/fbsearch/accounts — this endpoint will be deprecated soon. The current route doesn't support paging.
- `GET /v2/search/places` -- req: query
  - Prefer using /v3/fbsearch/places as this endpoint will be deprecated soon
- `GET /v2/search/reels` -- req: query -- opt: reels_max_id,rank_token
  - Prefer using /v3/fbsearch/reels as this endpoint will be deprecated soon
- `GET /v2/search/topsearch` -- req: query -- opt: next_max_id,rank_token,reels_max_id
  - Prefer using /v3/fbsearch/topsearch as this endpoint will be deprecated soon
- `GET /v2/user/medias` -- opt: user_id,page_id,safe_int
  - Prefer /gql/user/medias - this endpoint will be deprecated
- `GET /v2/user/videos` -- opt: user_id,page_id
  - Prefer using /v2/user/clips or /v2/user/medias instead
- `GET /v3/fbsearch/reels` -- req: query -- opt: reels_max_id
  - Deprecated due to pagination issues with duplicate results
- `GET /v3/fbsearch/topsearch` -- req: query -- opt: next_max_id
  - Prefer using /gql/topsearch as this endpoint has pagination issues with duplicate results
/**
 * TweetFeed frontend configuration.
 * Centralizes the data repo URL so it can be changed in ONE place.
 *
 * STAGE: fetches from 0xDanielLopez/tweetfeed-data-stage
 * PROD:  would fetch from 0xDanielLopez/TweetFeed
 */
(function(window) {
  'use strict';

  window.TweetFeed = window.TweetFeed || {};

  // Base URL for data CSV files (raw.githubusercontent). No trailing slash.
  window.TweetFeed.DATA_BASE = 'https://raw.githubusercontent.com/0xDanielLopez/TweetFeed/master';

  // Helper to build URLs for individual data files.
  window.TweetFeed.dataUrl = function(filename) {
    return window.TweetFeed.DATA_BASE + '/' + filename;
  };
})(window);

/**
 * TweetFeed shared utilities
 * Consolidates CSV parsing, HTML escaping, clipboard, CSV export, and number helpers
 * previously duplicated across 8+ HTML pages.
 */
(function(window) {
  'use strict';

  // ─── HTML escaping (XSS prevention) ────────────────────────────────────────
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ─── CSV parser (RFC 4180 compliant) ───────────────────────────────────────
  // Handles quoted fields, commas inside quoted fields, escaped quotes (""),
  // CRLF/LF line endings. Returns array of arrays (rows of fields).
  function parseCSV(text) {
    var rows = [];
    var row = [];
    var field = '';
    var inQuotes = false;
    var i = 0;
    var len = text.length;

    while (i < len) {
      var c = text.charAt(i);

      if (inQuotes) {
        if (c === '"') {
          if (text.charAt(i + 1) === '"') {
            // Escaped quote inside quoted field
            field += '"';
            i += 2;
            continue;
          }
          // End of quoted field
          inQuotes = false;
          i++;
          continue;
        }
        field += c;
        i++;
        continue;
      }

      if (c === '"' && field === '') {
        inQuotes = true;
        i++;
        continue;
      }
      if (c === ',') {
        row.push(field);
        field = '';
        i++;
        continue;
      }
      if (c === '\n' || c === '\r') {
        row.push(field);
        field = '';
        // Only push non-empty rows (ignore trailing empty lines)
        if (row.length > 1 || (row.length === 1 && row[0] !== '')) {
          rows.push(row);
        }
        row = [];
        if (c === '\r' && text.charAt(i + 1) === '\n') {
          i += 2;
        } else {
          i++;
        }
        continue;
      }
      field += c;
      i++;
    }

    // Handle last field/row if no trailing newline
    if (field !== '' || row.length > 0) {
      row.push(field);
      if (row.length > 1 || (row.length === 1 && row[0] !== '')) {
        rows.push(row);
      }
    }

    return rows;
  }

  // ─── Copy to clipboard (safe, via data-copy attr + event delegation) ───────
  // HTML should use: <i class="tf-copy" data-copy="VALUE">...</i>
  // VALUE must be HTML-escaped by the caller with escapeHtml()
  function copyToClipboard(text, $trigger) {
    var done = function(success) {
      if ($trigger && $trigger.length && success) {
        // If the trigger is a FontAwesome copy icon, swap to a green checkmark briefly
        if ($trigger.hasClass('fa-copy') || $trigger.hasClass('far') || $trigger.hasClass('fas')) {
          var origColor = $trigger.css('color');
          $trigger.removeClass('far fa-copy').addClass('fas fa-check').css('color', 'green');
          setTimeout(function() {
            $trigger.removeClass('fas fa-check').addClass('far fa-copy').css('color', origColor || '');
          }, 1000);
        } else {
          var $feedback = $('<span class="tf-copy-feedback" style="color:green;font-weight:bold;margin-left:4px;"> ✓</span>');
          $trigger.after($feedback);
          setTimeout(function() { $feedback.fadeOut(600, function() { $feedback.remove(); }); }, 800);
        }
      }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function() { done(true); },
        function() { fallbackCopy(text, done); }
      );
      return;
    }
    fallbackCopy(text, done);
  }

  function fallbackCopy(text, cb) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    if (cb) cb(ok);
  }

  // ─── CSV export ────────────────────────────────────────────────────────────
  // Escapes values per RFC 4180 (quote if contains comma/quote/newline)
  function escapeCsvField(v) {
    var s = (v === null || v === undefined) ? '' : String(v);
    if (s.indexOf('"') !== -1 || s.indexOf(',') !== -1 || s.indexOf('\n') !== -1 || s.indexOf('\r') !== -1) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }

  function downloadCSV(filename, rows) {
    var csv = rows.map(function(row) {
      return row.map(escapeCsvField).join(',');
    }).join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function exportTableToCSV(tableSelector, filename) {
    var $table = $(tableSelector);
    if (!$table.length) return;
    var rows = [];
    $table.find('tr').each(function() {
      var cols = [];
      $(this).find('th,td').each(function() {
        cols.push($(this).text().trim());
      });
      rows.push(cols);
    });
    downloadCSV(filename, rows);
  }

  // ─── Number / date helpers ─────────────────────────────────────────────────
  function addZero(n) {
    return n < 10 ? '0' + n : '' + n;
  }

  function numberFormat(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  // Replaces date.js Date.parse().toString("MMMM dS, yyyy HH:mm:ss UTC")
  var _months = ['January','February','March','April','May','June',
                 'July','August','September','October','November','December'];
  function _ordinal(d) {
    if (d === 1 || d === 21 || d === 31) return 'st';
    if (d === 2 || d === 22) return 'nd';
    if (d === 3 || d === 23) return 'rd';
    return 'th';
  }
  function formatDateLong(dateStr, parenTime) {
    var d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    var day = d.getUTCDate();
    var time = addZero(d.getUTCHours()) + ':' + addZero(d.getUTCMinutes()) + ':' + addZero(d.getUTCSeconds());
    if (parenTime) {
      return _months[d.getUTCMonth()] + ' ' + day + _ordinal(day) + ', ' + d.getUTCFullYear() + ' (' + time + ') UTC';
    }
    return _months[d.getUTCMonth()] + ' ' + day + _ordinal(day) + ', ' + d.getUTCFullYear() + ' ' + time + ' UTC';
  }

  // ─── AJAX wrapper with error handling ──────────────────────────────────────
  // Shows user-friendly error in the provided element on failure.
  function safeGet(url, options) {
    options = options || {};
    var onSuccess = options.success || function() {};
    var onError = options.error || function(msg) {
      console.error('[TweetFeed] Fetch failed:', url, msg);
      if (options.errorTarget) {
        var $target = $(options.errorTarget);
        if ($target.length) {
          $target.html('<p class="text-danger text-center" style="padding:1em;">⚠️ Error loading data. Please try again later.</p>');
        }
      }
    };
    return $.ajax({
      url: url,
      type: 'GET',
      timeout: options.timeout || 30000,
      success: onSuccess,
      error: function(xhr, status, err) {
        onError(status + ': ' + (err || 'unknown error'));
      }
    });
  }

  // ─── DataTable helpers (safe destroy before reinit) ────────────────────────
  function destroyDataTableIfExists(selector) {
    if ($.fn.DataTable && $.fn.DataTable.isDataTable(selector)) {
      $(selector).DataTable().destroy();
      // Clear tbody to prevent duplicate row accumulation
      $(selector).find('tbody').empty();
    }
  }

  // ─── Interval management (prevents memory leaks) ───────────────────────────
  var _intervals = [];
  function trackInterval(id) {
    _intervals.push(id);
    return id;
  }
  function clearTrackedIntervals() {
    _intervals.forEach(function(id) { clearInterval(id); });
    _intervals = [];
  }
  if (typeof window.addEventListener === 'function') {
    window.addEventListener('beforeunload', clearTrackedIntervals);
    window.addEventListener('pagehide', clearTrackedIntervals);
  }

  // ─── Global AJAX error handler ─────────────────────────────────────────────
  // Logs all failed AJAX requests (previously silent, leaving spinners spinning).
  // Individual pages can still add .fail() for page-specific UX.
  function initAjaxErrorHandler() {
    if (typeof $ === 'undefined') return;
    $(document).ajaxError(function(event, xhr, settings, error) {
      console.error('[TweetFeed] AJAX failed:', settings.url, xhr.status, error || xhr.statusText);
    });
  }
  if (typeof $ !== 'undefined') {
    $(initAjaxErrorHandler);
  } else {
    document.addEventListener('DOMContentLoaded', function() {
      if (typeof $ !== 'undefined') initAjaxErrorHandler();
    });
  }

  // ─── Event delegation for copy buttons ─────────────────────────────────────
  // Attach once per page load. Reads value from data-copy attribute.
  function initCopyDelegation() {
    if (typeof $ === 'undefined') return;
    $(document).off('click.tfcopy').on('click.tfcopy', '.tf-copy', function(e) {
      e.preventDefault();
      e.stopPropagation();
      var text = $(this).attr('data-copy') || '';
      if (!text) return;
      // Selector support: if data-copy starts with "#", copy the text
      // content of the referenced element (used on hunt.html command blocks).
      if (text.charAt(0) === '#') {
        var $target = $(text);
        if ($target.length) text = $target.text();
      }
      copyToClipboard(text, $(this));
    });
  }
  if (typeof $ !== 'undefined') {
    $(initCopyDelegation);
  } else {
    // Defer until jQuery loads
    document.addEventListener('DOMContentLoaded', function() {
      if (typeof $ !== 'undefined') initCopyDelegation();
    });
  }

  // ─── Expose public API ─────────────────────────────────────────────────────
  var api = {
    escapeHtml: escapeHtml,
    parseCSV: parseCSV,
    csvJSON: parseCSV,            // legacy alias (drop-in replacement)
    copyToClipboard: copyToClipboard,
    downloadCSV: downloadCSV,
    exportTableToCSV: exportTableToCSV,
    addZero: addZero,
    numberFormat: numberFormat,
    number_format: numberFormat,  // legacy alias (snake_case)
    formatDateLong: formatDateLong,
    safeGet: safeGet,
    destroyDataTableIfExists: destroyDataTableIfExists,
    trackInterval: trackInterval,
    clearTrackedIntervals: clearTrackedIntervals,
  };

  window.TweetFeed = window.TweetFeed || {};
  Object.assign(window.TweetFeed, api);

  // Legacy globals (for gradual migration from inline scripts)
  window.csvJSON = parseCSV;
  window.escapeHtml = escapeHtml;
  window.copyClipboard = function(text) { copyToClipboard(text, null); };
  window.addZero = addZero;
  window.number_format = numberFormat;
  window.formatDateLong = formatDateLong;

  // Legacy downloadCSV(csvString, filename) — matches the inline signature
  // used by 9 pages before dedupe. Writes a pre-joined CSV string as a Blob.
  window.downloadCSV = function(csv, filename) {
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Legacy exportTableToCSV(filename) — scrapes the first <table> on the
  // page starting at row index 2 (skipping header + DataTables filter row)
  // and downloads it. Used by 9 generic pages; index.html keeps its own
  // custom variant that does column skipping + URL extraction.
  if (!window.exportTableToCSV) {
    window.exportTableToCSV = function(filename) {
      var csv = [];
      var rows = document.querySelectorAll('table tr');
      for (var i = 2; i < rows.length; i++) {
        var row = [];
        var cols = rows[i].querySelectorAll('td, th');
        for (var j = 0; j < cols.length; j++) row.push(cols[j].innerText);
        csv.push(row.join(','));
      }
      window.downloadCSV(csv.join('\n'), filename);
    };
  }
})(window);

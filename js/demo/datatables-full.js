$(document).ready(function() {
    // Cell renderers for #dataTableFull (/search/). XSS-safe: every value is
    // escaped in attributes and text. Only type 'display' gets HTML; sorting and
    // searching read the plain field, so nothing walks the ~4,900 rows to prebuild
    // cells. 'filter' returns the ESCAPED field because
    // DataTables decodes HTML entities in filter data whenever it sees a '&'
    // (a raw "?a=1&section=2" would be searched as "?a=1§ion=2"); the decode
    // turns the escaped text back into the original, so search matches the
    // value exactly as before.
    function renderUser( user, type ) {
        if ( type === 'filter' ) { return escapeHtml( user ); }
        if ( type !== 'display' ) { return user; }
        var safeUser = /^[A-Za-z0-9_]{1,15}$/.test(user) ? user : '';
        var picSrc = '../pics/' + safeUser + '.png';
        return '<a class="twitterUser btn btn-primary btn-sm rounded btn-block" style="background-color: var(--tf-bg-1da1f2);border-color: var(--tf-bd-000);font-family: \'Rubik\', sans-serif;text-decoration: none;color: var(--tf-fg-fff);white-space: nowrap;" target="_blank" href="https://x.com/' + escapeHtml(user) + '" role="button" rel="noopener noreferrer"><img loading="lazy" width="20" height="20" src="' + picSrc + '" onerror="this.onerror=null;this.src=\'https://unavatar.io/twitter/' + safeUser + '\'" alt="' + escapeHtml(user) + '">&nbsp;' + escapeHtml(user) + '</a>';
    }

    function renderValue( value, type ) {
        if ( type === 'filter' ) { return escapeHtml( value ); }
        if ( type !== 'display' ) { return value; }
        return '<span style="display: block; width: 100%; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;"><i class="tf-copy far fa-copy" data-copy="' + escapeHtml(value) + '" role="button" tabindex="0" aria-label="Copy IOC value" title="Copy"></i> ' + escapeHtml(value) + '</span>';
    }

    function renderTweet( tweetUrl, type ) {
        // The link has no text, so the tweet URL must not become searchable.
        if ( type === 'filter' ) { return ''; }
        if ( type !== 'display' ) { return tweetUrl; }
        return '<a class="tf-action tf-action-tweet" target="_blank" href="' + escapeHtml(tweetUrl) + '" rel="noopener noreferrer" title="Open original tweet" aria-label="Open original tweet"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 1227" width="1em" height="1em" fill="currentColor" aria-hidden="true" style="vertical-align:-2px"><path d="M714.163 519.284 1160.89 0h-105.86L667.137 450.887 357.328 0H0l468.492 681.821L0 1226.37h105.866l409.625-476.152 327.181 476.152H1200L714.137 519.284h.026ZM569.165 687.828l-47.468-67.894-377.686-540.24h162.604l304.797 435.991 47.468 67.894 396.2 566.721H892.476L569.165 687.854v-.026Z"/></svg></a>';
    }

    function renderVirusTotal( data, type, row ) {
        if ( type === 'filter' ) { return ''; }
        if ( type !== 'display' ) { return row[3]; }
        var value = row[2] == 'url' ? encodeURIComponent(row[3]) : escapeHtml(row[3]);
        return '<a class="tf-action tf-action-vt" target="_blank" href="https://www.virustotal.com/gui/search/' + value + '" rel="noopener noreferrer" title="Search in VirusTotal" aria-label="Search in VirusTotal"><img loading="lazy" src="../img/vt.png" alt="VirusTotal" width="16" height="14"></a>';
    }

    // Setup - add a text input to each footer cell
    $('#dataTableFull thead tr').clone(true).appendTo( '#dataTableFull thead' );
    $('#dataTableFull thead tr:eq(1) th').each( function (i) {
        var title = $(this).text();
        // Icon-only columns (X, VirusTotal) have no text: a filter box there filters nothing.
        if ( !title.trim() ) { $(this).empty(); return; }
        $(this).html( '<input type="text" placeholder="'+title+'" />' );
 
        $( 'input', this ).on( 'keyup change', function () {
            if ( table.column(i).search() !== this.value ) {
                table
                    .column(i)
                    .search( this.value )
                    .draw();
            }
        } );
    } );
 
    var table = $('#dataTableFull').DataTable( {
        "pageLength": 10,
        orderCellsTop: true,
        fixedHeader: true,
        // deferRender: week.csv has ~4,900 rows; only the rows of the visible page
        // get a <tr>. Rows go in RAW ([date, user, type, value, tags, tweet_url]);
        // the User/Value/X/VT cell HTML is built by the render functions below, and
        // only when a cell is drawn (type 'display'). Mobile column classes come from
        // columns and the type tint (url/domain/ip/sha256/md5 -> the row colour)
        // from createdRow, so nothing has to touch every row after the data is added.
        deferRender: true,
        // Every column is declared type 'string': without it DataTables runs its type
        // detection over every cell of the 4,900 rows on rows.add, which doubled the
        // add+order+draw time. Dates ("YYYY-MM-DD HH:MM:SS") sort correctly as strings.
        // For Mobile: only show User (1), Value (3). Hide Date (0), Type (2), Tags (4), X (5), VT (6)
        columns: [
            // 0 Date
            { type: 'string', className: 'd-none d-lg-table-cell' },
            // 1 User: avatar button linking to the profile
            { type: 'string', render: renderUser },
            // 2 Type
            { type: 'string', className: 'd-none d-lg-table-cell' },
            // 3 Value: copy icon + escaped IOC
            { type: 'string', render: renderValue },
            // 4 Tags
            { type: 'string', className: 'd-none d-lg-table-cell tableTags' },
            // 5 X: icon link to the original tweet
            { type: 'string', className: 'd-none d-lg-table-cell', render: renderTweet },
            // 6 VT: not a CSV field, built from Type (2) and Value (3)
            { type: 'string', className: 'd-none d-lg-table-cell', data: null, render: renderVirusTotal }
        ],
        createdRow: function ( row, rowData ) {
            $(row).addClass( rowData[2] );
        },
        language: {
            // Custom empty-state messaging matching the design-system .empty-state
            // component (icon + headline + hint). Mirrors dashboard.html's
            // #emptyState pattern.
            emptyTable:
                '<div class="empty-state">' +
                '<div class="empty-icon"><i class="far fa-folder-open"></i></div>' +
                '<div class="empty-message">Loading IOCs…</div>' +
                '<div class="empty-hint">Fetching the last week of indicators.</div>' +
                '</div>',
            zeroRecords:
                '<div class="empty-state">' +
                '<div class="empty-icon"><i class="fas fa-search"></i></div>' +
                '<div class="empty-message">No IOCs match your search</div>' +
                '<div class="empty-hint">Try a broader query or remove a filter.</div>' +
                '</div>'
        }
    } );
} );
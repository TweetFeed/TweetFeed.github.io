$(document).ready(function() {
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
        // get a <tr>. Mobile column classes come from columnDefs and the type tint
        // (url/domain/ip/sha256/md5 -> the row colour) from createdRow, so nothing
        // has to touch every node after the data is added.
        deferRender: true,
        // For Mobile: only show User (1), Value (3). Hide Date (0), Type (2), Tags (4), X (5), VT (6)
        columnDefs: [
            { targets: [0, 2, 5, 6], className: 'd-none d-lg-table-cell' },
            { targets: 4, className: 'd-none d-lg-table-cell tableTags' }
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
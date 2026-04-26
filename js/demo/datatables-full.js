$(document).ready(function() {
    // Setup - add a text input to each footer cell
    $('#dataTableFull thead tr').clone(true).appendTo( '#dataTableFull thead' );
    $('#dataTableFull thead tr:eq(1) th').each( function (i) {
        var title = $(this).text();
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
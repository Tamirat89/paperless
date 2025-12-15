def migrate(cr, version):
    """
    Clean up orphaned quality inspection records that might cause '_unknown' object errors.
    """
    # Check if quality.inspection table exists
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'quality_inspection'
        );
    """)
    
    if not cr.fetchone()[0]:
        return
    
    # Clean up orphaned quality inspection records
    # Remove records where supplier_analysis_id doesn't exist
    cr.execute("""
        DELETE FROM quality_inspection 
        WHERE supplier_analysis_id NOT IN (
            SELECT id FROM supplier_analysis
        );
    """)
    
    # Clean up orphaned quality inspection line records
    # Remove records where quality_inspection_id doesn't exist
    cr.execute("""
        DELETE FROM quality_inspection_line 
        WHERE quality_inspection_id NOT IN (
            SELECT id FROM quality_inspection
        );
    """)
    
    # Clean up orphaned quality inspection line records
    # Remove records where supplier_analysis_line_id doesn't exist
    cr.execute("""
        DELETE FROM quality_inspection_line 
        WHERE supplier_analysis_line_id NOT IN (
            SELECT id FROM supplier_analysis_line
        );
    """)
    
    print("Migration completed: Cleaned up orphaned quality inspection records") 
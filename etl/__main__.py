import argparse
from .pipeline import run_pipeline

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 4 ETL Pipeline")
    parser.add_argument('--mode', choices=['full', 'incremental'], default='full', help='Run mode')
    parser.add_argument('--input-dir', type=str, help='Override input directory')
    parser.add_argument('--dry-run', action='store_true', help='Dry run without writing to DB')
    args = parser.parse_args()
    
    run_pipeline(mode=args.mode, data_dir=args.input_dir, dry_run=args.dry_run)

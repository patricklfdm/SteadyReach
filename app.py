"""Local 1D steady workflow entry point."""
import argparse
from ras_workflow import app_core

def main():
    p=argparse.ArgumentParser();p.add_argument('command',nargs='?',default='serve',choices=['serve','worker']);p.add_argument('record',nargs='?');p.add_argument('--no-browser',action='store_true');a=p.parse_args()
    if a.command=='worker':return app_core.worker(a.record)
    from ras_workflow.app_server import serve
    return serve(not a.no_browser)

if __name__=='__main__':raise SystemExit(main())

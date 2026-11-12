"""Invoke with the project .venv Python; no PowerShell policy change needed."""
if __name__ == '__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='doctor':
        from ras_workflow.doctor import main
        raise SystemExit(main(sys.argv[2:]))
    from ras_workflow.cli import main
    raise SystemExit(main())

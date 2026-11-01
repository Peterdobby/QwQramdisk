"""Compatibility entry point; use tools.verify_ios9 for any iOS 9 profile."""
from .verify_ios9 import ROOT, check, main

if __name__ == "__main__":
    main()

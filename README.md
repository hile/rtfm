
RTFM - local RFC cache with full text search
============================================

This package contains script to mirror RFC index and full text to local
directory, and to create a full text index based on whoosh to search the
contents of RFCs.

Data directories
----------------

Data is stored to ~/.cache/rtfm/ direcory.

Example Usage
=============

* rtfm update

    Downloads RFC index and missing RFC, updating whoosh cache automatically

* rtfm status

    Shows number of RFCs in local cache

* rtfm search keyword keyword

    Searches downloaded RFCs with whoosh for matching full keywords

* rtfm show 1234

    Shows RFC 1234 with PAGER or less if PAGER is not defined


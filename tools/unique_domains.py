#!/usr/bin/env python2.7
# get domains from list of URLs
# usage: unique_domains.py [<file>]

import sys
from urlparse import urlparse

all_urls = []
unique_domains = []

for fn in sys.argv[1:]:
    with open(fn) as f:
        all_urls.extend(f.readlines())

for url in all_urls:
    domain = urlparse(url).netloc

    if domain not in unique_domains:
        unique_domains.append(domain)

print('\n'.join(unique_domains))

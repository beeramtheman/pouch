# Pouch

## WTF is this

Pouch finds websites on the internet with \<script\> URLs matching a given
regex pattern.

This can be valuable when you realize how many products get users to embed
scripts and how many of those users provide contact information on their
websites.

## How

Pouch uses [Common Crawl][cc]'s WAT crawl data, which is updated roughly once a
month. The Bash code that actually scans a WAT archive file to produce results
is very simple and found in [scripts/matches][matches]. Results are the URLs of
the web pages containing matching \<script\> tags. Of course doing this at
scale gets a bit more complicated, which is what Pouch is for.

```bash
grep -B7 '"Scripts":.*"url":"'$REGEXP'"' records.wat"
| awk '/^WARC-Target-URI/ {print $2}'
```

Crawl archives released by Common Crawl are split into thousands of WAT files
(they have other formats as well, but Pouch uses WAT). When they release a new
archive they provide a "path" file that has the paths of all WAT files from
that release for download on AWS S3. To use Pouch, download the latest WAT path
file from Common Crawl's website and save it decompressed as *wat.paths* in the
root of this repo.

Pouch can then use a variety of AWS services to efficiently and quickly
download/decompress/scan every (or up to a limit provided in
[config.ini][config.ini]) WAT file given in *wat.paths* and save results in one
central S3 bucket.

Please read the comments above each option in config.ini before running Pouch.
Options can be left unset, you will be prompted to fill these out every time
Pouch is run. The defaults are either required or what I found to work best and
should probably be left alone unless your willing to spend time and money
playing with things.

Read the license for this repo. I am not liable for any AWS fees.

## Program flow

### 0) *starting program*
- `./pouch.py`
- *fill out options not set in config.ini*
- *do stuff unrelated to Pouch because Pouch is now running*

### 1) pouch.py
- [pouch.py][pouch.py] writes WAT paths from *wat.paths* to a new AWS SQS queue
- [pouch.py][pouch.py] launches AWS EC2 instances and copies the scripts into them
- [pouch.py][pouch.py] runs [setup][setup] on all EC2 instances

### 2) setup
- [setup][setup] installs necessary programs etc
- [setup][setup] runs threads of [matches][matches]
- [setup][setup] waits until 0 threads of [matches][matches] are running before proceeding to step 4

### 3) matches
- [matches][matches] requests a message (WAT path) from SQS queue
- if no message exists
    - all WAT files have been or are currently being downloaded/scanned so [matches][matches] exits
- if message received
    - [matches][matches] downloads and decompresses the .wat.gz file from the path received
    - [matches][matches] scans the .wat file and appends results (URLs) to the results file
    - [matches][matches] deletes the .wat file, *launches another thread of [matches][matches]*, and exits

### 4) setup
- [setup][setup] uploads the results file to a pre-made S3 bucket

## Benchmarks

The time it takes Pouch to scan a WAT file depends greatly on how many matches
there are. The more matches, the longer it takes. The more instances used, the
less time it takes, so you will not be paying more except for the storage costs
(by default 11 GB per instance). Below is a single benchmark of a full run
(Pouch can cost pennies to run if you reduce the path cap). If you use Pouch
yourself please consider sharing stats.

- Goal
    - Find websites using the latest [Stripe.js][stripe.js] (note: only a subset of Stripe customers)

- Options
    - Path cap: 33002
    - Instances: 4
    - Regex: `.*js\.stripe\.com\/v2.*`
    - *all others are defaults in this repo*

- Process
    - Time taken: ~30 hours
    - Cost: ~$39

- Results
    - URLs: 96216
    - Unique domains: 1322 ([/tools/unique_domains.py][unique_domains.py])

[cc]: https://commoncrawl.org/
[config.ini]: config.ini
[pouch.py]: pouch.py
[setup]: scripts/setup
[matches]: scripts/matches
[stripe.js]: https://stripe.com/docs/stripe.js
[unique_domains.py]: tools/unique_domains.py

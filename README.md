# Planet Clojure

This is the source code of [Planet Clojure](https://planet.clojure.in),
which collects posts from blogs about Clojure into one page and one Atom feed.

The template of Planet Clojure was designed by [Brajeshwar](https://brajeshwar.com); so all credit goes to him.

## Adding yourself to Planet Clojure

If you have a blog on Clojure and want to feature on Planet Clojure, fork this project on GitHub,
edit the file `config.ini` and add your blog's feed URL and your name in the following format:

```text
[https://path/to/your/blog/feed/]
name = Your Name
```

Then send a pull request.
We will be happy to add you to Planet Clojure.

Please add a feed which contains only posts related to Clojure or Lisp.
As a policy we do not put generic feeds on Planet Clojure.
If your site has no Clojure-specific feed, you may add a `filter` to the section, so that only Clojure posts are shown:

```text
filter = (clojure|Clojure|\(def |\(defn-? )
```

The filter is a case-sensitive regular expression, matched against each post's title, text, author and tags.
It may not be very precise if your feed doesn't include enough text for it to match.

If you also have a Twitter account, please add a `twitter` line to the section:

```text
twitter = <handle-without-@>
```

## Reporting bugs

If you have an issue with the design or the site, please open an issue, or send a pull request with the fix.
We will be happy to merge it.

## How it works

Once an hour, an AWS Lambda function:

1. reads `config.ini`, downloaded from this repository when
   `PLANET_CONFIG_URL` is set, else the copy built into its image;
2. fetches all feeds concurrently, using conditional requests, one request at
   a time per host, and backing off feeds that keep failing;
3. filters and sanitizes the posts, and keeps the 10 newest of each feed in a
   SQLite cache stored in S3;
4. renders `index.html` and `atom.xml` and uploads them, with `static/`, to an
   S3 bucket served by CloudFront.

| Path                    | What                                                  |
| ----------------------- | ----------------------------------------------------- |
| `config.ini`            | site settings and feed subscriptions                  |
| `src/planet/`           | the job: fetch, parse, filter, store, render, publish |
| `src/planet/templates/` | page and feed templates (Jinja2)                      |
| `static/`               | CSS, images and scripts for the page                  |
| `infra/`                | AWS CDK stack                                         |
| `tests/`                | tests, including the CDK stack                        |

## Development

Requires [uv](https://docs.astral.sh/uv/).
Docker is needed for the local Lambda run.

```sh
uv sync
scripts/check.sh      # format, lint, strict type check, dead code, tests
```

Run once locally, writing the site to `local/output`:

```sh
uv run planet --cache local/cache.sqlite --out local/output
uv run python -m http.server -d local/output 8000
```

Run the Lambda image locally against a fake S3 ([floci](https://github.com/floci-io/floci)):

```sh
docker compose up --build -d
scripts/invoke.sh                 # one run
scripts/pull-site.sh              # copy the site to local/site
uv run python -m http.server -d local/site 8000
docker compose down               # also discards the fake S3
```

## Licence

MIT.
See [LICENSE](LICENSE).

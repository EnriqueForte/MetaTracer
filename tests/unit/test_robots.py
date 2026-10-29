"""robots.txt courtesy: parse rules, never treat them as authorization."""

from metatracer.core.safety.http import USER_AGENT
from metatracer.extractors.robots import parse_robots, parse_sitemap


def test_star_group_disallow_is_a_prefix_and_allow_wins_when_longer() -> None:
    policy = parse_robots(
        "User-agent: *\nDisallow: /private/\nAllow: /private/public.pdf\n"
    )
    assert policy.allows("https://target.com/ok.pdf") is True
    assert policy.allows("https://target.com/private/secret.pdf") is False
    assert policy.allows("https://target.com/private/public.pdf") is True


def test_our_group_replaces_star_it_does_not_merge() -> None:
    # The MetaTracer group is the only one that applies. The `*` Disallow of
    # /secret does not carry over.
    policy = parse_robots(
        "User-agent: *\n"
        "Disallow: /secret\n"
        "\n"
        "User-agent: MetaTracer\n"
        "Disallow: /private\n",
        user_agent=USER_AGENT,
    )
    assert "metatracer" in USER_AGENT.lower()
    assert policy.allows("https://target.com/secret.pdf") is True
    assert policy.allows("https://target.com/private/file.pdf") is False


def test_another_bot_does_not_block_us() -> None:
    policy = parse_robots("User-agent: Googlebot\nDisallow: /\n")
    assert policy.allows("https://target.com/admin") is True


def test_empty_disallow_and_crawl_delay_do_not_block() -> None:
    policy = parse_robots(
        "User-agent: *\nDisallow:\nCrawl-delay: 100\nSitemap: https://target.com/sitemap.xml\n"
    )
    assert policy.allows("https://target.com/") is True
    assert policy.sitemaps == ("https://target.com/sitemap.xml",)


def test_end_anchor_and_wildcard() -> None:
    policy = parse_robots("User-agent: *\nDisallow: /*.pdf$\n")
    assert policy.allows("https://target.com/report.pdf") is False
    assert policy.allows("https://target.com/report.pdf.txt") is True
    assert policy.allows("https://target.com/page.html") is True


def test_query_string_is_part_of_the_match() -> None:
    policy = parse_robots("User-agent: *\nDisallow: /download\n")
    assert policy.allows("https://target.com/download?id=7") is False


def test_sitemap_index_and_malformed_xml() -> None:
    kind, locs = parse_sitemap(
        b"""<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://target.com/a.xml</loc></sitemap>
          <sitemap><loc> </loc></sitemap>
        </sitemapindex>"""
    )
    assert kind == "index"
    assert locs == ("https://target.com/a.xml",)
    assert parse_sitemap(b"<not xml") == ("urlset", ())


def test_unreadable_body_is_not_a_policy() -> None:
    # The caller treats a missing file as allow-all. The parser of an empty
    # body agrees: there is nothing to honor.
    policy = parse_robots("")
    assert policy.allows("https://target.com/anything") is True
    assert policy.sitemaps == ()

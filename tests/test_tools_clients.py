import pytest

from engine.tools import arxiv, cache, crossref, openalex, semanticscholar


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)


def test_openalex_search_normalizes_and_reconstructs_abstract(monkeypatch):
    monkeypatch.setattr(
        openalex,
        "_fetch",
        lambda query, limit: [
            {
                "title": "Agentic Supply Chains",
                "doi": "https://doi.org/10.1234/abc",
                "publication_year": 2024,
                "cited_by_count": 12,
                "abstract_inverted_index": {"Agents": [0], "help": [1], "supply": [2], "chains": [3]},
                "primary_location": {"source": {"display_name": "Journal of AI"}},
                "authorships": [{"author": {"display_name": "A. Researcher"}}],
            }
        ],
    )
    results = openalex.search("supply chain agents")
    assert len(results) == 1
    r = results[0]
    assert r.title == "Agentic Supply Chains"
    assert r.doi == "10.1234/abc"
    assert r.abstract == "Agents help supply chains"
    assert r.authors == ["A. Researcher"]
    assert r.source == "openalex"


def test_openalex_drops_untitled_works(monkeypatch):
    monkeypatch.setattr(openalex, "_fetch", lambda query, limit: [{"title": ""}])
    assert openalex.search("x") == []


def test_semanticscholar_search_normalizes(monkeypatch):
    monkeypatch.setattr(
        semanticscholar,
        "_fetch",
        lambda query, limit: [
            {
                "title": "LLM Exception Handling",
                "abstract": "We study exceptions.",
                "year": 2023,
                "venue": "NeurIPS",
                "externalIds": {"DOI": "10.5/x", "ArXiv": "2301.00001"},
                "citationCount": 5,
                "authors": [{"name": "B. Smith"}],
            }
        ],
    )
    results = semanticscholar.search("llm exceptions")
    assert results[0].arxiv_id == "2301.00001"
    assert results[0].source == "semanticscholar"


def test_arxiv_parses_atom_feed(monkeypatch):
    xml_text = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>  Agentic Exception Handling
    in Supply Chains </title>
    <summary>An abstract.</summary>
    <published>2023-01-05T00:00:00Z</published>
    <author><name>C. Author</name></author>
  </entry>
</feed>"""
    monkeypatch.setattr(arxiv, "_fetch_search", lambda query, limit: xml_text)
    results = arxiv.search("agentic exception handling")
    assert len(results) == 1
    assert results[0].arxiv_id == "2301.00001v1"
    assert results[0].year == 2023
    assert results[0].source == "arxiv"
    assert "\n" not in results[0].title


def test_arxiv_get_by_id(monkeypatch):
    xml_text = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>A Paper</title>
    <summary>Abstract.</summary>
    <published>2023-01-05T00:00:00Z</published>
  </entry>
</feed>"""
    monkeypatch.setattr(arxiv, "_fetch_by_id", lambda arxiv_id: xml_text)
    result = arxiv.get_by_id("2301.00001")
    assert result is not None
    assert result.title == "A Paper"


def test_arxiv_get_by_id_not_found(monkeypatch):
    empty_feed = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    monkeypatch.setattr(arxiv, "_fetch_by_id", lambda arxiv_id: empty_feed)
    assert arxiv.get_by_id("9999.99999") is None


def test_crossref_get_by_doi(monkeypatch):
    monkeypatch.setattr(
        crossref,
        "_fetch_by_doi",
        lambda doi: {
            "title": ["Real Paper"],
            "DOI": "10.1/real",
            "author": [{"given": "D", "family": "Author"}],
            "published": {"date-parts": [[2022, 3]]},
            "container-title": ["Some Journal"],
        },
    )
    result = crossref.get_by_doi("10.1/real")
    assert result.title == "Real Paper"
    assert result.year == 2022
    assert result.authors == ["D Author"]


def test_crossref_get_by_doi_not_found(monkeypatch):
    monkeypatch.setattr(crossref, "_fetch_by_doi", lambda doi: None)
    assert crossref.get_by_doi("10.1/fake-hallucinated-doi") is None


def test_all_retry_decorators_reraise_the_real_exception():
    # Regression test: tenacity wraps the final exception in an opaque
    # RetryError by default (RetryError[<Future ... raised HTTPStatusError>]),
    # hiding the actual status code/URL. reraise=True makes it propagate the
    # real exception instead -- this is the config property that was missing,
    # not something worth simulating real network retries (with real backoff
    # delays) to exercise.
    decorated_fetch_fns = [
        openalex._fetch,
        semanticscholar._fetch,
        arxiv._fetch_search,
        arxiv._fetch_by_id,
        crossref._fetch_by_doi,
        crossref._fetch_search,
    ]
    for fn in decorated_fetch_fns:
        assert fn.retry.reraise is True, f"{fn.__module__}.{fn.__name__} doesn't reraise the real exception"

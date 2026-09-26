import os
import json
import requests
from datetime import datetime, timedelta


# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = os.environ.get(
    "AMC_API_KEY",
    "KEY"
)

BASE_URL = "https://api.amctheatres.com"

HEADERS = {
    "X-AMC-Vendor-Key": API_KEY,
    "Accept": "application/json",
}

# Add your theaters here.
THEATERS = {
    "AMC Kent Station": "606",
    "AMC Southcenter": "607",

    # Examples:
    # "AMC Southcenter 16": "123",
    # "AMC Alderwood Mall 16": "456",
}

DAYS_TO_FETCH = 7

OUTPUT_FILE = "amc.html"

# Set this to a movie ID if you want the complete
# Movie API response printed for debugging.
#
# Set to None when you are done debugging.
DEBUG_MOVIE_ID = "84764"


# ============================================================
# API HELPER
# ============================================================

def api_get(url, params=None):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.HTTPError as e:

        print(f"API HTTP error: {e}")

        try:
            print(response.text[:2000])
        except Exception:
            pass

        return None

    except requests.exceptions.RequestException as e:

        print(f"API request error: {e}")

        return None

    except ValueError as e:

        print(f"Invalid JSON response: {e}")

        return None


# ============================================================
# THEATER
# ============================================================

def get_theatre(theatre_id):

    url = f"{BASE_URL}/v2/theatres/{theatre_id}"

    return api_get(url)


def get_theatre_name(theatre_id, fallback):

    data = get_theatre(theatre_id)

    if not data:
        return fallback

    for key in (
        "name",
        "theatreName",
        "longName",
        "shortName"
    ):

        value = data.get(key)

        if value:
            return str(value)

    return fallback


# ============================================================
# SHOWTIMES
# ============================================================

def get_showtimes(theatre_id, date):

    date_string = date.strftime("%m-%d-%Y")

    url = (
        f"{BASE_URL}/v2/theatres/"
        f"{theatre_id}/showtimes/{date_string}"
    )

    data = api_get(
        url,
        params={
            "page-size": 200
        }
    )

    if not data:
        return []

    embedded = data.get(
        "_embedded",
        {}
    )

    showtimes = embedded.get(
        "showtimes",
        []
    )

    if isinstance(showtimes, list):
        return showtimes

    return []


# ============================================================
# MOVIE API
# ============================================================

def get_movie(movie_id):

    if not movie_id:
        return None

    url = (
        f"{BASE_URL}/v2/movies/{movie_id}"
    )

    return api_get(url)


# ============================================================
# MOVIE ID
# ============================================================

def get_movie_id(showtime):

    movie_id = showtime.get(
        "movieId"
    )

    if movie_id:
        return str(movie_id)

    movie_id = showtime.get(
        "titleId"
    )

    if movie_id:
        return str(movie_id)

    links = showtime.get(
        "_links",
        {}
    )

    if isinstance(links, dict):

        for key, value in links.items():

            if "movie" not in key.lower():
                continue

            if not isinstance(
                value,
                dict
            ):
                continue

            href = value.get(
                "href",
                ""
            )

            if not href:
                continue

            parts = href.rstrip(
                "/"
            ).split("/")

            candidate = parts[-1]

            if candidate.isdigit():
                return candidate

    return None


# ============================================================
# MOVIE TITLE
# ============================================================

def movie_title(showtime):

    return (
        showtime.get(
            "movieName"
        )
        or showtime.get(
            "sortableTitleName"
        )
        or "Unknown Movie"
    )


# ============================================================
# GENERIC HELPERS
# ============================================================

def first_value(data, *keys):

    if not isinstance(
        data,
        dict
    ):
        return None

    for key in keys:

        value = data.get(key)

        if value not in (
            None,
            "",
            [],
            {}
        ):
            return value

    return None


def extract_text(value):

    if value is None:
        return ""

    if isinstance(
        value,
        str
    ):
        return value.strip()

    if isinstance(
        value,
        (int, float)
    ):
        return str(value)

    if isinstance(
        value,
        list
    ):

        parts = []

        for item in value:

            text = extract_text(
                item
            )

            if text:
                parts.append(
                    text
                )

        return ", ".join(parts)

    if isinstance(
        value,
        dict
    ):

        for key in (
            "name",
            "title",
            "value",
            "description",
            "text",
            "label"
        ):

            if value.get(key):

                return extract_text(
                    value[key]
                )

    return ""


# ============================================================
# MOVIE METADATA
# ============================================================

def get_synopsis(movie):

    if not movie:
        return ""

    return extract_text(
        first_value(
            movie,
            "synopsis",
            "description",
            "plot",
            "overview",
            "summary"
        )
    )


def get_genre(movie):

    if not movie:
        return ""

    return extract_text(
        first_value(
            movie,
            "genre",
            "genres",
            "movieGenres"
        )
    )


def get_rating(movie):

    if not movie:
        return ""

    return extract_text(
        first_value(
            movie,
            "mpaaRating",
            "rating",
            "contentRating"
        )
    )


def get_runtime(movie):

    if not movie:
        return ""

    value = first_value(
        movie,
        "runTime",
        "runtime",
        "runtimeMinutes",
        "duration"
    )

    if isinstance(
        value,
        (int, float)
    ):

        return f"{int(value)} min"

    return extract_text(value)


def get_directors(movie):

    if not movie:
        return ""

    return extract_text(
        first_value(
            movie,
            "directors",
            "director"
        )
    )


def get_cast(movie):

    if not movie:
        return ""

    return extract_text(
        first_value(
            movie,
            "actors",
            "cast",
            "castMembers"
        )
    )


# ============================================================
# ARTWORK
# ============================================================

def get_media(movie):

    if not isinstance(
        movie,
        dict
    ):
        return {}

    media = movie.get(
        "media"
    )

    if isinstance(
        media,
        dict
    ):
        return media

    return {}


def get_poster_url(
    movie,
    showtime=None,
    debug=False
):
    """
    AMC Movie API artwork.

    Priority:

    1. media.posterDynamic
    2. other poster fields
    3. media.heroDesktopDynamic
    4. showtime media poster
    5. showtime media hero
    """

    media = get_media(
        movie
    )

    if debug:

        print()
        print(
            "      ARTWORK DATA:"
        )

        print(
            json.dumps(
                media,
                indent=2,
                ensure_ascii=False
            )
        )

    # --------------------------------------------------------
    # 1. Actual poster
    # --------------------------------------------------------

    poster = media.get(
        "posterDynamic"
    )

    if isinstance(
        poster,
        str
    ) and poster.strip():

        if debug:

            print(
                "      POSTER FOUND:"
            )

            print(
                "        Path: "
                "root.media.posterDynamic"
            )

            print(
                f"        URL:  {poster}"
            )

        return poster.strip()

    # --------------------------------------------------------
    # 2. Other possible poster fields
    # --------------------------------------------------------

    for key in (
        "poster",
        "posterUrl",
        "posterURL",
        "posterDynamicUrl",
        "posterDynamicURL"
    ):

        value = media.get(
            key
        )

        if isinstance(
            value,
            str
        ) and value.strip():

            if debug:

                print(
                    "      POSTER FOUND:"
                )

                print(
                    f"        Path: "
                    f"root.media.{key}"
                )

                print(
                    f"        URL:  {value}"
                )

            return value.strip()

    # --------------------------------------------------------
    # 3. Hero fallback
    # --------------------------------------------------------

    hero = media.get(
        "heroDesktopDynamic"
    )

    if isinstance(
        hero,
        str
    ) and hero.strip():

        if debug:

            print(
                "      NO POSTER FOUND."
            )

            print(
                "      Using hero image "
                "as fallback:"
            )

            print(
                f"        URL:  {hero}"
            )

        return hero.strip()

    # --------------------------------------------------------
    # 4. Showtime media
    # --------------------------------------------------------

    if showtime:

        showtime_media = (
            showtime.get(
                "media"
            )
        )

        if isinstance(
            showtime_media,
            dict
        ):

            poster = (
                showtime_media.get(
                    "posterDynamic"
                )
            )

            if isinstance(
                poster,
                str
            ) and poster.strip():

                if debug:

                    print(
                        "      POSTER FOUND "
                        "IN SHOWTIME MEDIA:"
                    )

                    print(
                        f"        URL: {poster}"
                    )

                return poster.strip()

            hero = (
                showtime_media.get(
                    "heroDesktopDynamic"
                )
            )

            if isinstance(
                hero,
                str
            ) and hero.strip():

                if debug:

                    print(
                        "      HERO FOUND "
                        "IN SHOWTIME MEDIA:"
                    )

                    print(
                        f"        URL: {hero}"
                    )

                return hero.strip()

    # --------------------------------------------------------
    # Nothing
    # --------------------------------------------------------

    if debug:

        print(
            "      NO ARTWORK FOUND."
        )

    return ""


# ============================================================
# POSTER DEBUG
# ============================================================

def debug_movie_response(
    movie_id,
    title,
    movie
):

    if DEBUG_MOVIE_ID is None:
        return

    if str(movie_id) != str(
        DEBUG_MOVIE_ID
    ):
        return

    print()
    print()
    print("#" * 80)

    print(
        f"POSTER DEBUG FOR: "
        f"{title}"
    )

    print(
        f"MOVIE ID: {movie_id}"
    )

    print("#" * 80)

    if not movie:

        print()
        print(
            "Movie API returned NO DATA."
        )

        print(
            "#" * 80
        )

        return

    print()
    print(
        "COMPLETE MOVIE API RESPONSE:"
    )

    print()

    print(
        json.dumps(
            movie,
            indent=2,
            ensure_ascii=False
        )
    )

    print()
    print(
        "-" * 80
    )

    print(
        "ARTWORK INFORMATION:"
    )

    print(
        "-" * 80
    )

    poster = get_poster_url(
        movie,
        debug=True
    )

    print()

    if poster:

        print(
            "FINAL SELECTED IMAGE:"
        )

        print(
            poster
        )

    else:

        print(
            "NO IMAGE WAS SELECTED."
        )

    print()
    print(
        "#" * 80
    )

    print()


# ============================================================
# SHOWTIME DISPLAY
# ============================================================

def showtime_time(showtime):

    value = showtime.get(
        "showDateTimeLocal"
    )

    if not value:
        return "Unknown Time"

    try:

        dt = datetime.fromisoformat(
            value
        )

        try:

            return dt.strftime(
                "%-I:%M %p"
            )

        except ValueError:

            return dt.strftime(
                "%#I:%M %p"
            )

    except Exception:

        return str(value)


def get_auditorium(showtime):

    auditorium = showtime.get(
        "auditorium"
    )

    if auditorium is None:
        return ""

    return (
        f"Auditorium "
        f"{auditorium}"
    )


def get_attributes(showtime):

    attributes = showtime.get(
        "attributes",
        []
    )

    result = []

    if isinstance(
        attributes,
        list
    ):

        for attr in attributes:

            if isinstance(
                attr,
                dict
            ):

                name = attr.get(
                    "name"
                )

                if name:
                    result.append(
                        name
                    )

            elif attr:

                result.append(
                    str(attr)
                )

    return result


def get_purchase_url(showtime):

    return (
        showtime.get(
            "purchaseUrl"
        )
        or showtime.get(
            "mobilePurchaseUrl"
        )
        or "#"
    )


# ============================================================
# MOVIE ENTRY
# ============================================================

def build_movie_entry(
    showtime,
    date,
    movie_cache
):

    title = movie_title(
        showtime
    )

    movie_id = get_movie_id(
        showtime
    )

    # --------------------------------------------------------
    # Fetch movie details once
    # --------------------------------------------------------

    if (
        movie_id
        and movie_id not in movie_cache
    ):

        print(
            f"      Fetching movie "
            f"information for "
            f"{title} ({movie_id})..."
        )

        movie_cache[movie_id] = (
            get_movie(movie_id)
        )

        debug_movie_response(
            movie_id,
            title,
            movie_cache[movie_id]
        )

    movie = movie_cache.get(
        movie_id
    )

    # --------------------------------------------------------
    # Showtime entry
    # --------------------------------------------------------

    entry = {

        "date":
            date.strftime(
                "%A, %B %-d"
            ),

        "date_iso":
            date.isoformat(),

        "time":
            showtime_time(
                showtime
            ),

        "auditorium":
            get_auditorium(
                showtime
            ),

        "attributes":
            get_attributes(
                showtime
            ),

        "purchase_url":
            get_purchase_url(
                showtime
            ),

        "sold_out":
            bool(
                showtime.get(
                    "isSoldOut",
                    False
                )
            ),

        "almost_sold_out":
            bool(
                showtime.get(
                    "isAlmostSoldOut",
                    False
                )
            ),

        "cancelled":
            bool(
                showtime.get(
                    "isCanceled",
                    False
                )
            ),
    }

    return entry, movie


# ============================================================
# MOVIE INFO
# ============================================================

def movie_info_from_movie(
    movie,
    fallback_showtime
):

    info = {

        "description":
            "",

        "genre":
            "",

        "rating":
            "",

        "runtime":
            "",

        "directors":
            "",

        "cast":
            "",

        "poster":
            "",
    }

    if movie:

        info["description"] = (
            get_synopsis(
                movie
            )
        )

        info["genre"] = (
            get_genre(
                movie
            )
        )

        info["rating"] = (
            get_rating(
                movie
            )
        )

        info["runtime"] = (
            get_runtime(
                movie
            )
        )

        info["directors"] = (
            get_directors(
                movie
            )
        )

        info["cast"] = (
            get_cast(
                movie
            )
        )

        info["poster"] = (
            get_poster_url(
                movie,
                fallback_showtime
            )
        )

    return info


# ============================================================
# BUILD THEATER DATA
# ============================================================

def build_theatre_data():

    all_theatres = {}

    today = datetime.now().date()

    for (
        configured_name,
        theatre_id
    ) in THEATERS.items():

        print()
        print("=" * 60)

        print(
            f"Theater: "
            f"{configured_name}"
        )

        print(
            f"ID: {theatre_id}"
        )

        print("=" * 60)

        actual_name = (
            get_theatre_name(
                theatre_id,
                configured_name
            )
        )

        print(
            f"AMC name: "
            f"{actual_name}"
        )

        movies = {}

        movie_cache = {}

        # ----------------------------------------------------
        # Seven days
        # ----------------------------------------------------

        for day_offset in range(
            DAYS_TO_FETCH
        ):

            date = (
                today
                + timedelta(
                    days=day_offset
                )
            )

            print(
                f"  Fetching showtimes for "
                f"{date.strftime('%Y-%m-%d')}..."
            )

            showtimes = get_showtimes(
                theatre_id,
                date
            )

            print(
                f"    Found "
                f"{len(showtimes)} "
                f"showtimes"
            )

            # ------------------------------------------------
            # Individual showtimes
            # ------------------------------------------------

            for showtime in showtimes:

                title = movie_title(
                    showtime
                )

                movie_id = get_movie_id(
                    showtime
                )

                if title not in movies:

                    movies[title] = {

                        "movie_id":
                            movie_id,

                        "info":
                            {},

                        "showtimes":
                            []
                    }

                entry, movie = (
                    build_movie_entry(
                        showtime,
                        date,
                        movie_cache
                    )
                )

                if not movies[title][
                    "info"
                ]:

                    movies[title][
                        "info"
                    ] = (
                        movie_info_from_movie(
                            movie,
                            showtime
                        )
                    )

                if (
                    not movies[title][
                        "movie_id"
                    ]
                    and movie_id
                ):

                    movies[title][
                        "movie_id"
                    ] = movie_id

                movies[title][
                    "showtimes"
                ].append(
                    entry
                )

        # ----------------------------------------------------
        # Sort movies alphabetically
        # ----------------------------------------------------

        sorted_movies = {}

        for title in sorted(
            movies.keys(),
            key=lambda x: x.lower()
        ):

            sorted_movies[title] = (
                movies[title]
            )

        all_theatres[
            theatre_id
        ] = {

            "id":
                theatre_id,

            "name":
                actual_name,

            "movies":
                sorted_movies
        }

    return all_theatres


# ============================================================
# HTML
# ============================================================

def generate_html(data):

    theater_data_json = json.dumps(
        data,
        ensure_ascii=False
    )

    html = r"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>AMC Showtimes</title>


<style>


* {
    box-sizing: border-box;
}


html,
body {

    margin: 0;
    padding: 0;

    width: 100%;
    height: 100%;

    overflow: hidden;

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    background: #101114;

    color: #f0f1f3;
}


button,
input {
    font: inherit;
}


/* ============================================================
   THEATER TABS
   ============================================================ */

.theater-tabs {

    height: 58px;

    display: flex;

    align-items: center;

    gap: 8px;

    padding: 8px 12px;

    background: #15171b;

    border-bottom:
        1px solid #292c33;

    overflow-x: auto;

    overflow-y: hidden;

    white-space: nowrap;
}


.theater-tab {

    flex: 0 0 auto;

    border:
        1px solid #30343c;

    background: #1d2025;

    color: #c9ccd2;

    border-radius: 8px;

    padding: 9px 14px;

    cursor: pointer;

    transition:
        background .15s,
        border-color .15s;
}


.theater-tab:hover {

    background: #252930;

    color: white;
}


.theater-tab.active {

    background: #e31b23;

    border-color: #e31b23;

    color: white;

    font-weight: 600;
}


/* ============================================================
   PAGE
   ============================================================ */

.page {

    display: flex;

    width: 100%;

    height:
        calc(100vh - 58px);

    min-height: 0;
}


/* ============================================================
   SIDEBAR
   ============================================================ */

.sidebar {

    width: 280px;

    min-width: 280px;

    height: 100%;

    display: flex;

    flex-direction: column;

    background: #191b20;

    border-right:
        1px solid #292c33;

    overflow: hidden;
}


.sidebar-header {

    padding: 14px;

    border-bottom:
        1px solid #292c33;
}


.sidebar-title {

    font-size: 16px;

    font-weight: 700;

    margin-bottom: 9px;
}


.search {

    width: 100%;

    padding: 9px 10px;

    border-radius: 7px;

    border:
        1px solid #343840;

    background: #111318;

    color: white;

    outline: none;
}


.search:focus {

    border-color: #e31b23;
}


/* ============================================================
   MOVIE LIST
   ============================================================ */

.movie-list {

    flex: 1 1 0;

    min-height: 0;

    height: 0;

    overflow-y: auto;

    overflow-x: hidden;

    padding: 7px;
}


.movie-button {

    width: 100%;

    display: block;

    text-align: left;

    border: 0;

    border-radius: 7px;

    background: transparent;

    color: #c9ccd2;

    padding: 10px;

    margin-bottom: 3px;

    cursor: pointer;
}


.movie-button:hover {

    background: #24272d;

    color: white;
}


.movie-button.active {

    background: #30343c;

    color: white;
}


.movie-button-title {

    font-size: 14px;

    font-weight: 600;

    line-height: 1.3;
}


.movie-button-count {

    font-size: 11px;

    color: #8e939d;

    margin-top: 3px;
}


/* ============================================================
   CONTENT
   ============================================================ */

.content {

    flex: 1;

    min-width: 0;

    min-height: 0;

    height: 100%;

    overflow-y: auto;

    padding: 22px;
}


/* ============================================================
   MOVIE INFO
   ============================================================ */

.movie-info {

    display: flex;

    gap: 20px;

    margin-bottom: 24px;

    padding-bottom: 22px;

    border-bottom:
        1px solid #292c33;
}


.poster {

    flex:
        0 0 150px;

    width: 150px;

    height: 225px;

    object-fit: cover;

    border-radius: 9px;

    background: #1b1d22;

    border:
        1px solid #30343a;
}


.poster-placeholder {

    flex:
        0 0 150px;

    width: 150px;

    height: 225px;

    border-radius: 9px;

    background:
        linear-gradient(
            145deg,
            #202329,
            #15171b
        );

    border:
        1px solid #30343a;

    display: flex;

    align-items: center;

    justify-content: center;

    color: #666b74;

    font-size: 13px;

    text-align: center;

    padding: 20px;
}


.movie-details {

    min-width: 0;
}


.movie-title {

    font-size: 28px;

    line-height: 1.15;

    font-weight: 750;

    margin-bottom: 9px;
}


.movie-meta {

    display: flex;

    flex-wrap: wrap;

    gap: 7px;

    margin-bottom: 14px;
}


.meta-badge {

    background: #24272d;

    border:
        1px solid #333740;

    border-radius: 5px;

    padding: 4px 8px;

    color: #bfc3ca;

    font-size: 12px;
}


.description {

    max-width: 900px;

    color: #b8bcc4;

    line-height: 1.55;

    font-size: 14px;

    white-space: pre-line;
}


.credits {

    margin-top: 12px;

    color: #858a94;

    font-size: 12px;

    line-height: 1.5;
}


/* ============================================================
   DAYS
   ============================================================ */

.day {

    margin-bottom: 20px;
}


.day-header {

    display: flex;

    align-items: center;

    gap: 9px;

    margin-bottom: 7px;
}


.day-title {

    font-size: 17px;

    font-weight: 700;

    color: #f1f2f4;
}


.today-badge {

    background: #e31b23;

    color: white;

    border-radius: 4px;

    padding: 2px 6px;

    font-size: 9px;

    font-weight: 800;

    letter-spacing: .4px;
}


/* ============================================================
   COMPACT SHOWTIMES
   ============================================================ */

.showtime-list {

    display: flex;

    flex-direction: column;

    gap: 4px;
}


.showtime {

    width: 100%;

    height: 38px;

    min-height: 38px;

    display: grid;

    grid-template-columns:
        85px
        1fr
        auto;

    align-items: center;

    gap: 10px;

    padding: 5px 10px;

    border:
        1px solid #292c33;

    border-radius: 5px;

    background: #191b20;

    text-decoration: none;

    color: inherit;
}


.showtime:hover {

    background: #22252b;

    border-color: #414650;
}


.showtime-time {

    font-weight: 700;

    font-size: 13px;

    color: white;

    white-space: nowrap;
}


.showtime-info {

    min-width: 0;

    display: flex;

    align-items: center;
}


.auditorium {

    color: #858a94;

    font-size: 11px;

    white-space: nowrap;

    overflow: hidden;

    text-overflow: ellipsis;
}


/*
    AMC attributes are still fetched by Python,
    but hidden from the compact dashboard.
*/

.attribute {

    display: none;
}


.status {

    display: flex;

    align-items: center;

    justify-content: flex-end;

    gap: 4px;

    white-space: nowrap;
}


.status-badge {

    border-radius: 3px;

    padding: 2px 6px;

    font-size: 9px;

    font-weight: 700;

    white-space: nowrap;
}


.sold-out {

    background: #5c2226;

    color: #ffb8bd;
}


.almost {

    background: #594719;

    color: #ffe29a;
}


.cancelled {

    background: #3d3d3d;

    color: #d0d0d0;
}


/* ============================================================
   EMPTY
   ============================================================ */

.empty {

    padding: 50px 20px;

    text-align: center;

    color: #737882;
}


.no-results {

    padding: 20px 10px;

    text-align: center;

    color: #777c85;

    font-size: 13px;
}


/* ============================================================
   MOBILE
   ============================================================ */

@media (max-width: 700px) {

    html,
    body {

        overflow: auto;
    }


    .page {

        height: auto;

        min-height:
            calc(100vh - 58px);

        display: flex;

        flex-direction: column;
    }


    .sidebar {

        width: 100%;

        min-width: 0;

        height: 260px;

        min-height: 260px;

        border-right: none;

        border-bottom:
            1px solid #292c33;
    }


    .movie-list {

        height: 0;

        flex: 1 1 0;
    }


    .content {

        height: auto;

        overflow: visible;

        padding: 16px;
    }


    .movie-info {

        gap: 14px;
    }


    .poster,
    .poster-placeholder {

        flex-basis: 105px;

        width: 105px;

        height: 158px;
    }


    .movie-title {

        font-size: 22px;
    }


    .showtime {

        grid-template-columns:
            75px
            1fr
            auto;

        gap: 7px;

        height: 36px;

        min-height: 36px;

        padding: 4px 7px;
    }


    .showtime-time {

        font-size: 12px;
    }


    .auditorium {

        font-size: 10px;
    }


    .status {

        justify-content: flex-end;
    }

}


@media (max-width: 480px) {

    .movie-info {

        flex-direction: column;
    }


    .poster,
    .poster-placeholder {

        width: 130px;

        height: 195px;

        flex-basis: auto;
    }


    .showtime {

        grid-template-columns:
            70px
            1fr
            auto;

        gap: 5px;

        padding-left: 6px;

        padding-right: 6px;
    }

}


</style>

</head>


<body>


<div
    class="theater-tabs"
    id="theaterTabs"
></div>


<div class="page">


    <aside class="sidebar">

        <div class="sidebar-header">

            <div
                class="sidebar-title"
                id="sidebarTitle"
            >
                Movies
            </div>


            <input
                id="movieSearch"
                class="search"
                type="text"
                placeholder="Search movies..."
            >

        </div>


        <div
            class="movie-list"
            id="movieList"
        ></div>

    </aside>


    <main
        class="content"
        id="content"
    ></main>


</div>


<script>


const DATA =
    __AMC_DATA_PLACEHOLDER__;


let activeTheaterId = null;

let activeMovieTitle = null;


/* ============================================================
   HELPERS
   ============================================================ */

function escapeHtml(value) {

    if (
        value === null ||
        value === undefined
    ) {

        return "";
    }

    return String(value)
        .replaceAll(
            "&",
            "&amp;"
        )
        .replaceAll(
            "<",
            "&lt;"
        )
        .replaceAll(
            ">",
            "&gt;"
        )
        .replaceAll(
            '"',
            "&quot;"
        )
        .replaceAll(
            "'",
            "&#039;"
        );
}


function getTheaterIds() {

    return Object.keys(
        DATA
    );
}


function currentTheater() {

    if (!activeTheaterId) {
        return null;
    }

    return DATA[
        activeTheaterId
    ];
}


function currentMovies() {

    const theater =
        currentTheater();

    if (!theater) {
        return {};
    }

    return theater.movies || {};
}


function totalShowtimes(movie) {

    if (
        !movie ||
        !movie.showtimes
    ) {

        return 0;
    }

    return movie.showtimes.length;
}


/* ============================================================
   THEATER TABS
   ============================================================ */

function renderTheaterTabs() {

    const container =
        document.getElementById(
            "theaterTabs"
        );

    container.innerHTML = "";

    for (
        const id
        of getTheaterIds()
    ) {

        const theater =
            DATA[id];

        const button =
            document.createElement(
                "button"
            );

        button.className =
            "theater-tab";

        if (
            id ===
            activeTheaterId
        ) {

            button.classList.add(
                "active"
            );
        }

        button.textContent =
            theater.name || id;

        button.addEventListener(
            "click",
            () => {

                activeTheaterId =
                    id;

                activeMovieTitle =
                    null;

                renderTheaterTabs();

                renderSidebar();

                const titles =
                    Object.keys(
                        currentMovies()
                    );

                if (
                    titles.length > 0
                ) {

                    activeMovieTitle =
                        titles[0];

                    renderSidebar();

                    renderMovie();
                }

                else {

                    document.getElementById(
                        "content"
                    ).innerHTML =
                        '<div class="empty">' +
                        'No movies found for this theater.' +
                        '</div>';
                }
            }
        );

        container.appendChild(
            button
        );
    }
}


/* ============================================================
   SIDEBAR
   ============================================================ */

function renderSidebar() {

    const list =
        document.getElementById(
            "movieList"
        );

    const title =
        document.getElementById(
            "sidebarTitle"
        );

    const theater =
        currentTheater();

    if (!theater) {

        list.innerHTML = "";

        return;
    }

    title.textContent =
        theater.name ||
        "Movies";

    const search =
        document
            .getElementById(
                "movieSearch"
            )
            .value
            .trim()
            .toLowerCase();

    list.innerHTML = "";

    const movies =
        currentMovies();

    let visibleCount = 0;

    for (
        const [
            movieTitle,
            movie
        ]
        of Object.entries(movies)
    ) {

        if (
            search &&
            !movieTitle
                .toLowerCase()
                .includes(search)
        ) {

            continue;
        }

        visibleCount++;

        const button =
            document.createElement(
                "button"
            );

        button.className =
            "movie-button";

        if (
            movieTitle ===
            activeMovieTitle
        ) {

            button.classList.add(
                "active"
            );
        }

        const titleDiv =
            document.createElement(
                "div"
            );

        titleDiv.className =
            "movie-button-title";

        titleDiv.textContent =
            movieTitle;

        const countDiv =
            document.createElement(
                "div"
            );

        countDiv.className =
            "movie-button-count";

        countDiv.textContent =
            totalShowtimes(movie) +
            " showtimes";

        button.appendChild(
            titleDiv
        );

        button.appendChild(
            countDiv
        );

        button.addEventListener(
            "click",
            () => {

                activeMovieTitle =
                    movieTitle;

                renderSidebar();

                renderMovie();
            }
        );

        list.appendChild(
            button
        );
    }

    if (
        visibleCount === 0
    ) {

        list.innerHTML =
            '<div class="no-results">' +
            'No movies found.' +
            '</div>';
    }
}


/* ============================================================
   MOVIE INFO
   ============================================================ */

function renderMovieInfo(
    title,
    movie
) {

    const info =
        movie.info || {};

    let posterHtml = "";


    if (info.poster) {

        posterHtml =
            '<img class="poster" ' +
            'src="' +
            escapeHtml(
                info.poster
            ) +
            '" ' +
            'alt="' +
            escapeHtml(title) +
            ' poster" ' +
            'loading="lazy">';
    }

    else {

        posterHtml =
            '<div class="poster-placeholder">' +
            'No artwork available' +
            '</div>';
    }


    let badges = "";


    if (info.rating) {

        badges +=
            '<span class="meta-badge">' +
            escapeHtml(
                info.rating
            ) +
            '</span>';
    }


    if (info.runtime) {

        badges +=
            '<span class="meta-badge">' +
            escapeHtml(
                info.runtime
            ) +
            '</span>';
    }


    if (info.genre) {

        badges +=
            '<span class="meta-badge">' +
            escapeHtml(
                info.genre
            ) +
            '</span>';
    }


    let credits = "";


    if (info.directors) {

        credits +=
            "<div>" +
            "<strong>Director:</strong> " +
            escapeHtml(
                info.directors
            ) +
            "</div>";
    }


    if (info.cast) {

        credits +=
            "<div>" +
            "<strong>Cast:</strong> " +
            escapeHtml(
                info.cast
            ) +
            "</div>";
    }


    return (

        '<section class="movie-info">' +

            posterHtml +

            '<div class="movie-details">' +

                '<div class="movie-title">' +
                    escapeHtml(title) +
                '</div>' +

                (
                    badges
                    ?
                    '<div class="movie-meta">' +
                        badges +
                    '</div>'
                    :
                    ""
                ) +

                (
                    info.description
                    ?
                    '<div class="description">' +
                        escapeHtml(
                            info.description
                        ) +
                    '</div>'
                    :
                    ""
                ) +

                (
                    credits
                    ?
                    '<div class="credits">' +
                        credits +
                    '</div>'
                    :
                    ""
                ) +

            '</div>' +

        '</section>'
    );
}


/* ============================================================
   SHOWTIME
   ============================================================ */

function renderShowtime(
    showtime
) {

    /*
        Attributes intentionally aren't rendered here.
        This keeps each showtime row compact.
    */

    let status = "";


    if (
        showtime.sold_out
    ) {

        status +=
            '<span class="status-badge sold-out">' +
            'Sold Out' +
            '</span>';
    }

    else if (
        showtime.almost_sold_out
    ) {

        status +=
            '<span class="status-badge almost">' +
            'Almost Sold Out' +
            '</span>';
    }


    if (
        showtime.cancelled
    ) {

        status +=
            '<span class="status-badge cancelled">' +
            'Cancelled' +
            '</span>';
    }


    const url =
        showtime.purchase_url ||
        "#";


    return (

        '<a class="showtime" ' +

        (
            showtime.cancelled
            ?
            ""
            :
            'href="' +
            escapeHtml(url) +
            '" ' +
            'target="_blank" ' +
            'rel="noopener"'
        ) +

        '>' +

            '<div class="showtime-time">' +
                escapeHtml(
                    showtime.time
                ) +
            '</div>' +

            '<div class="showtime-info">' +

                (
                    showtime.auditorium
                    ?
                    '<span class="auditorium">' +
                        escapeHtml(
                            showtime.auditorium
                        ) +
                    '</span>'
                    :
                    ""
                ) +

            '</div>' +

            '<div class="status">' +
                status +
            '</div>' +

        '</a>'
    );
}


/* ============================================================
   MOVIE PAGE
   ============================================================ */

function renderMovie() {

    const content =
        document.getElementById(
            "content"
        );

    const movies =
        currentMovies();

    const movie =
        movies[
            activeMovieTitle
        ];

    if (!movie) {

        content.innerHTML =
            '<div class="empty">' +
            'Select a movie.' +
            '</div>';

        return;
    }


    let html =
        renderMovieInfo(
            activeMovieTitle,
            movie
        );


    const grouped = {};


    for (
        const showtime
        of (
            movie.showtimes ||
            []
        )
    ) {

        if (
            !grouped[
                showtime.date_iso
            ]
        ) {

            grouped[
                showtime.date_iso
            ] = {

                label:
                    showtime.date,

                showtimes:
                    []
            };
        }


        grouped[
            showtime.date_iso
        ].showtimes.push(
            showtime
        );
    }


    const dates =
        Object.keys(
            grouped
        ).sort();


    /*
        Use the browser's local date rather than
        UTC so TODAY doesn't shift around midnight.
    */

    const now =
        new Date();

    const year =
        now.getFullYear();

    const month =
        String(
            now.getMonth() + 1
        ).padStart(
            2,
            "0"
        );

    const day =
        String(
            now.getDate()
        ).padStart(
            2,
            "0"
        );

    const todayIso =
        `${year}-${month}-${day}`;


    for (
        const date
        of dates
    ) {

        const dayData =
            grouped[date];


        dayData.showtimes.sort(
            (a, b) =>
                a.time.localeCompare(
                    b.time
                )
        );


        const isToday =
            date === todayIso;


        html +=
            '<section class="day">' +

                '<div class="day-header">' +

                    '<div class="day-title">' +
                        escapeHtml(
                            dayData.label
                        ) +
                    '</div>' +

                    (
                        isToday
                        ?
                        '<span class="today-badge">' +
                        'TODAY' +
                        '</span>'
                        :
                        ""
                    ) +

                '</div>' +

                '<div class="showtime-list">';


        for (
            const showtime
            of dayData.showtimes
        ) {

            html +=
                renderShowtime(
                    showtime
                );
        }


        html +=
                '</div>' +
            '</section>';
    }


    content.innerHTML =
        html;
}


/* ============================================================
   SEARCH
   ============================================================ */

document
    .getElementById(
        "movieSearch"
    )
    .addEventListener(
        "input",
        () => {

            renderSidebar();
        }
    );


/* ============================================================
   INITIALIZE
   ============================================================ */

const theaterIds =
    getTheaterIds();


if (
    theaterIds.length > 0
) {

    activeTheaterId =
        theaterIds[0];

    renderTheaterTabs();


    const movies =
        Object.keys(
            currentMovies()
        );


    if (
        movies.length > 0
    ) {

        activeMovieTitle =
            movies[0];
    }


    renderSidebar();

    renderMovie();

}

else {

    document.getElementById(
        "content"
    ).innerHTML =
        '<div class="empty">' +
        'No theaters configured.' +
        '</div>';
}


</script>


</body>

</html>
"""


    # IMPORTANT:
    #
    # This must NOT be a Python f-string.
    # The JavaScript contains many { } characters.
    #
    # We inject the JSON separately.

    html = html.replace(
        "__AMC_DATA_PLACEHOLDER__",
        theater_data_json
    )

    return html


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "Fetching AMC showtimes..."
    )
    print()

    data = build_theatre_data()

    html = generate_html(
        data
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html)

    print()
    print("=" * 60)

    print(
        f"Done! Created: "
        f"{OUTPUT_FILE}"
    )

    print("=" * 60)
    print()
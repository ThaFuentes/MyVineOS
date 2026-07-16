# Public-domain hymn starter pack for Worship Team library.
# Only includes material generally accepted as public domain in the US (lyrics).
# Chord symbols are simple common progressions for church use — not commercial charts.
# Leaders choose which titles to add to their library.

from __future__ import annotations

from typing import Any

# Each pack item:
#   id, title, artist/origin, copyright_line, ccli_song_number (often empty for PD),
#   tags, lyrics_raw (ChordPro-friendly with section markers)

PUBLIC_DOMAIN_PACK: list[dict[str, Any]] = [
    {
        'id': 'amazing-grace',
        'title': 'Amazing Grace',
        'artist': 'John Newton',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'grace', 'classic'],
        'lyrics_raw': """[Verse 1]
[G]Amazing [G7]grace how [C]sweet the [G]sound
That saved a [Em]wretch like [D]me
I [G]once was [G7]lost but [C]now am [G]found
Was blind but [D]now I [G]see

[Verse 2]
[G]'Twas grace that [G7]taught my [C]heart to [G]fear
And grace my [Em]fears re[D]lieved
How [G]precious [G7]did that [C]grace ap[G]pear
The hour I [D]first be[G]lieved

[Verse 3]
[G]Through many [G7]dangers [C]toils and [G]snares
I have al[Em]ready [D]come
'Tis [G]grace hath [G7]brought me [C]safe thus [G]far
And grace will [D]lead me [G]home

[Verse 4]
[G]When we've been [G7]there ten [C]thousand [G]years
Bright shining [Em]as the [D]sun
We've [G]no less [G7]days to [C]sing God's [G]praise
Than when we [D]first be[G]gun
""",
    },
    {
        'id': 'holy-holy-holy',
        'title': 'Holy, Holy, Holy',
        'artist': 'Reginald Heber / John B. Dykes',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'trinity', 'classic'],
        'lyrics_raw': """[Verse 1]
[D]Holy holy [A]holy [Bm]Lord God Al[A]mighty
[D]Early in the [G]morning our [A]song shall rise to [D]Thee
[D]Holy holy [A]holy [Bm]merciful and [A]mighty
[D]God in three [G]Persons [A]blessed Trini[D]ty

[Verse 2]
[D]Holy holy [A]holy [Bm]all the saints a[A]dore Thee
[D]Casting down their [G]golden crowns a[A]round the glassy [D]sea
[D]Cherubim and [A]seraphim [Bm]falling down be[A]fore Thee
[D]Which wert and [G]art and [A]evermore shall [D]be

[Verse 3]
[D]Holy holy [A]holy [Bm]though the darkness [A]hide Thee
[D]Though the eye of [G]sinful man Thy [A]glory may not [D]see
[D]Only Thou art [A]holy [Bm]there is none be[A]side Thee
[D]Perfect in [G]power in [A]love and puri[D]ty
""",
    },
    {
        'id': 'be-thou-my-vision',
        'title': 'Be Thou My Vision',
        'artist': 'Traditional Irish / Eleanor Hull (tr.)',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'devotion', 'classic'],
        'lyrics_raw': """[Verse 1]
[D]Be Thou my [G]Vision O [D]Lord of my [A]heart
[Bm]Naught be all [G]else to me [A]save that Thou [D]art
[G]Thou my best [D]thought by [G]day or by [D]night
[Bm]Waking or [G]sleeping Thy [A]presence my [D]light

[Verse 2]
[D]Be Thou my [G]Wisdom and [D]Thou my true [A]Word
[Bm]I ever [G]with Thee and [A]Thou with me [D]Lord
[G]Thou my great [D]Father I [G]Thy true [D]son
[Bm]Thou in me [G]dwelling and [A]I with Thee [D]one

[Verse 3]
[D]Riches I [G]heed not nor [D]man's empty [A]praise
[Bm]Thou mine in[G]heritance [A]now and [D]always
[G]Thou and Thou [D]only first [G]in my [D]heart
[Bm]High King of [G]heaven my [A]Treasure Thou [D]art

[Verse 4]
[D]High King of [G]heaven my [D]victory [A]won
[Bm]May I reach [G]heaven's joys O [A]bright heaven's [D]Sun
[G]Heart of my [D]own heart what[G]ever be[D]fall
[Bm]Still be my [G]Vision O [A]Ruler of [D]all
""",
    },
    {
        'id': 'it-is-well',
        'title': 'It Is Well with My Soul',
        'artist': 'Horatio Spafford / Philip Bliss',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'peace', 'classic'],
        'lyrics_raw': """[Verse 1]
[C]When peace like a [G]river at[C]tendeth my [F]way
When [C]sorrows like [Am]sea billows [G]roll
What[C]ever my [F]lot Thou hast [C]taught me to [F]say
It is [C]well it is [G]well with my [C]soul

[Chorus]
It is [C]well (it is well)
With my [G]soul (with my soul)
It is [F]well it is [C]well with my [G]soul

[Verse 2]
[C]Though Satan should [G]buffet though [C]trials should [F]come
Let [C]this blest as[Am]surance con[G]trol
That [C]Christ has re[F]garded my [C]helpless es[F]tate
And has [C]shed His own [G]blood for my [C]soul

[Verse 3]
[C]My sin oh the [G]bliss of this [C]glorious [F]thought
My [C]sin not in [Am]part but the [G]whole
Is [C]nailed to the [F]cross and I [C]bear it no [F]more
Praise the [C]Lord praise the [G]Lord O my [C]soul
""",
    },
    {
        'id': 'come-thou-fount',
        'title': 'Come Thou Fount of Every Blessing',
        'artist': 'Robert Robinson',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'grace', 'classic'],
        'lyrics_raw': """[Verse 1]
[D]Come Thou Fount of [G]every [D]blessing
Tune my [G]heart to [A]sing Thy [D]grace
Streams of mercy [G]never [D]ceasing
Call for [G]songs of [A]loudest [D]praise
Teach me some me[G]lodious [D]sonnet
Sung by [G]flaming [A]tongues a[D]bove
Praise the mount I'm [G]fixed up[D]on it
Mount of [G]Thy re[A]deeming [D]love

[Verse 2]
[D]Here I raise my [G]Ebene[D]zer
Hither [G]by Thy [A]help I've [D]come
And I hope by [G]Thy good [D]pleasure
Safely [G]to ar[A]rive at [D]home
Jesus sought me [G]when a [D]stranger
Wandering [G]from the [A]fold of [D]God
He to rescue [G]me from [D]danger
Inter[G]posed His [A]precious [D]blood

[Verse 3]
[D]O to grace how [G]great a [D]debtor
Daily [G]I'm con[A]strained to [D]be
Let Thy goodness [G]like a [D]fetter
Bind my [G]wandering [A]heart to [D]Thee
Prone to wander [G]Lord I [D]feel it
Prone to [G]leave the [A]God I [D]love
Here's my heart O [G]take and [D]seal it
Seal it [G]for Thy [A]courts a[D]bove
""",
    },
    {
        'id': 'what-a-friend',
        'title': 'What a Friend We Have in Jesus',
        'artist': 'Joseph Scriven / Charles Converse',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'prayer', 'classic'],
        'lyrics_raw': """[Verse 1]
[F]What a friend we [C]have in [F]Jesus
All our [Bb]sins and [C]griefs to [F]bear
What a privilege [C]to [F]carry
Everything to [C]God in [F]prayer
O what peace we [Bb]often [F]forfeit
O what [Bb]needless [C]pain we [F]bear
All because we [C]do not [F]carry
Everything to [C]God in [F]prayer

[Verse 2]
[F]Have we trials [C]and temp[F]tations
Is there [Bb]trouble [C]any[F]where
We should never [C]be dis[F]couraged
Take it to the [C]Lord in [F]prayer
Can we find a [Bb]friend so [F]faithful
Who will [Bb]all our [C]sorrows [F]share
Jesus knows our [C]every [F]weakness
Take it to the [C]Lord in [F]prayer
""",
    },
    {
        'id': 'a-mighty-fortress',
        'title': 'A Mighty Fortress Is Our God',
        'artist': 'Martin Luther',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'reformation', 'classic'],
        'lyrics_raw': """[Verse 1]
[C]A mighty fortress [G]is our [C]God
A bulwark [F]never [G]fail[C]ing
Our helper He a[G]mid the [C]flood
Of mortal [F]ills pre[G]vail[C]ing
For still our [Am]ancient [G]foe
Doth seek to [C]work us [F]woe
His craft and [C]power are [G]great
And armed with [Am]cruel [F]hate
On earth is [G]not his [C]equal

[Verse 2]
[C]Did we in our own [G]strength con[C]fide
Our striving [F]would be [G]los[C]ing
Were not the right man [G]on our [C]side
The man of [F]God's own [G]choos[C]ing
Dost ask who [Am]that may [G]be
Christ Jesus [C]it is [F]He
Lord Saba[C]oth His [G]name
From age to [Am]age the [F]same
And He must [G]win the [C]battle
""",
    },
    {
        'id': 'when-i-survey',
        'title': 'When I Survey the Wondrous Cross',
        'artist': 'Isaac Watts',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'cross', 'classic'],
        'lyrics_raw': """[Verse 1]
[D]When I survey the [A]wondrous [D]cross
On which the [G]Prince of [A]glory [D]died
My richest gain I [A]count but [D]loss
And pour con[G]tempt on [A]all my [D]pride

[Verse 2]
[D]Forbid it Lord that [A]I should [D]boast
Save in the [G]death of [A]Christ my [D]God
All the vain things that [A]charm me [D]most
I sacrifice [G]them to [A]His [D]blood

[Verse 3]
[D]See from His head His [A]hands His [D]feet
Sorrow and [G]love flow [A]mingled [D]down
Did e'er such love and [A]sorrow [D]meet
Or thorns com[G]pose so [A]rich a [D]crown

[Verse 4]
[D]Were the whole realm of [A]nature [D]mine
That were a [G]present [A]far too [D]small
Love so amazing [A]so di[D]vine
Demands my [G]soul my [A]life my [D]all
""",
    },
    {
        'id': 'doxology',
        'title': 'Doxology (Praise God From Whom All Blessings Flow)',
        'artist': 'Thomas Ken',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'praise', 'classic', 'short'],
        'lyrics_raw': """[Verse 1]
[G]Praise God from [D]whom all [Em]blessings [D]flow
[G]Praise Him all [C]creatures [G]here be[D]low
[G]Praise Him a[D]bove ye [Em]heavenly [C]host
[G]Praise Father [C]Son and [D]Holy [G]Ghost
[G]A[C]men
""",
    },
    {
        'id': 'nothing-but-the-blood',
        'title': 'Nothing but the Blood',
        'artist': 'Robert Lowry',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'blood', 'classic'],
        'lyrics_raw': """[Verse 1]
[G]What can wash a[D]way my [G]sin
Nothing but the [D]blood of [G]Jesus
What can make me [D]whole a[G]gain
Nothing but the [D]blood of [G]Jesus

[Chorus]
O [G]precious is the [C]flow
That [G]makes me white as [D]snow
No [G]other fount I [C]know
Nothing but the [D]blood of [G]Jesus

[Verse 2]
[G]For my pardon [D]this I [G]see
Nothing but the [D]blood of [G]Jesus
For my cleansing [D]this my [G]plea
Nothing but the [D]blood of [G]Jesus
""",
    },
    {
        'id': 'blessed-assurance',
        'title': 'Blessed Assurance',
        'artist': 'Fanny Crosby / Phoebe Knapp',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'assurance', 'classic'],
        'lyrics_raw': """[Verse 1]
[C]Blessed as[G]surance [C]Jesus is [F]mine
O [C]what a [Am]foretaste of [D]glory di[G]vine
[C]Heir of sal[G]vation [C]purchase of [F]God
Born of His [C]Spirit [G]washed in His [C]blood

[Chorus]
This is my [F]story this is my [C]song
Praising my [Am]Savior [D]all the day [G]long
This is my [F]story this is my [C]song
Praising my [Am]Savior [G]all the day [C]long

[Verse 2]
[C]Perfect sub[G]mission [C]perfect de[F]light
Visions of [C]rapture now [Am]burst on my [D]sight [G]
[C]Angels de[G]scending [C]bring from a[F]bove
Echoes of [C]mercy [G]whispers of [C]love
""",
    },
    {
        'id': 'jesus-paid-it-all',
        'title': 'Jesus Paid It All',
        'artist': 'Elvina Hall / John Grape',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'cross', 'classic'],
        'lyrics_raw': """[Verse 1]
[D]I hear the Savior [A]say
Thy strength indeed is [D]small
Child of weakness [G]watch and pray
Find in [D]Me thine [A]all in [D]all

[Chorus]
[D]Jesus paid it [A]all
All to Him I [D]owe
Sin had left a [G]crimson stain
He washed it [D]white as [A]snow [D]

[Verse 2]
[D]Lord now indeed I [A]find
Thy power and Thine a[D]lone
Can change the leper's [G]spots
And melt the [D]heart of [A]stone [D]
""",
    },
    {
        'id': 'i-surrender-all',
        'title': 'I Surrender All',
        'artist': 'Judson Van DeVenter / Winfield Weeden',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'surrender', 'classic'],
        'lyrics_raw': """[Verse 1]
[D]All to Jesus [A]I sur[D]render
All to [G]Him I [A]freely [D]give
I will ever [A]love and [D]trust Him
In His [G]presence [A]daily [D]live

[Chorus]
I sur[A]render [D]all
I sur[A]render [D]all
All to [G]Thee my [D]blessed [G]Savior
I sur[D]render [A]all [D]

[Verse 2]
[D]All to Jesus [A]I sur[D]render
Humbly [G]at His [A]feet I [D]bow
Worldly pleasures [A]all for[D]saken
Take me [G]Jesus [A]take me [D]now
""",
    },
    {
        'id': 'at-the-cross',
        'title': 'At the Cross (Alas and Did My Savior Bleed)',
        'artist': 'Isaac Watts / Ralph Hudson',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'cross', 'classic'],
        'lyrics_raw': """[Verse 1]
[G]Alas and did my [D]Savior [G]bleed
And did my [C]Sovereign [G]die
Would He devote that [D]sacred [G]head
For sinners [D]such as [G]I

[Chorus]
At the [C]cross at the [G]cross
Where I [D]first saw the [G]light
And the [C]burden of my [G]heart rolled a[D]way
It was [G]there by faith I re[C]ceived my sight
And now [G]I am [D]happy all the [G]day

[Verse 2]
[G]Was it for crimes that [D]I have [G]done
He groaned up[C]on the [G]tree
Amazing pity [D]grace un[G]known
And love be[D]yond de[G]gree
""",
    },
    {
        'id': 'rock-of-ages',
        'title': 'Rock of Ages',
        'artist': 'Augustus Toplady / Thomas Hastings',
        'copyright_line': 'Public Domain',
        'ccli_song_number': '',
        'tags': ['hymn', 'refuge', 'classic'],
        'lyrics_raw': """[Verse 1]
[G]Rock of Ages [C]cleft for [G]me
Let me hide my[D]self in [G]Thee
Let the water [C]and the [G]blood
From Thy wounded [D]side which [G]flowed
Be of sin the [C]double [G]cure
Save from wrath and [D]make me [G]pure

[Verse 2]
[G]Not the labors [C]of my [G]hands
Can fulfill Thy [D]law's de[G]mands
Could my zeal no [C]respite [G]know
Could my tears for[D]ever [G]flow
All for sin could [C]not a[G]tone
Thou must save and [D]Thou a[G]lone
""",
    },
]


def list_public_domain_pack() -> list[dict]:
    """Return pack metadata for UI (without full lyrics until expanded)."""
    out = []
    for item in PUBLIC_DOMAIN_PACK:
        out.append({
            'id': item['id'],
            'title': item['title'],
            'artist': item.get('artist') or '',
            'copyright_line': item.get('copyright_line') or 'Public Domain',
            'ccli_song_number': item.get('ccli_song_number') or '',
            'tags': item.get('tags') or [],
            'preview': (item.get('lyrics_raw') or '')[:220].replace('\n', ' '),
            'has_chords': '[' in (item.get('lyrics_raw') or '') and ']' in (item.get('lyrics_raw') or ''),
        })
    return out


def get_public_domain_song(pack_id: str) -> dict | None:
    for item in PUBLIC_DOMAIN_PACK:
        if item['id'] == pack_id:
            return dict(item)
    return None


def get_public_domain_songs(pack_ids: list[str]) -> list[dict]:
    wanted = set(pack_ids or [])
    return [dict(item) for item in PUBLIC_DOMAIN_PACK if item['id'] in wanted]

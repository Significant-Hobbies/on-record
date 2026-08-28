import { describe, expect, it } from 'vitest';
import { referenceAssertion, sanitizeReferences } from './references';

const segment =
  'I still recommend The Sovereign Individual, and personally I use Cursor every day.';

describe('sanitizeReferences', () => {
  it('keeps names that appear in the claim quote', () => {
    const refs = sanitizeReferences(
      [
        { kind: 'book', name: 'The Sovereign Individual', role: 'recommends' },
        { kind: 'app', name: 'Cursor', role: 'uses' },
      ],
      segment
    );
    expect(refs).toHaveLength(2);
  });

  it('drops hallucinated titles', () => {
    const refs = sanitizeReferences(
      [{ kind: 'book', name: 'Invented Title', role: 'recommends' }],
      segment
    );
    expect(refs).toEqual([]);
  });

  it('drops a name that appears elsewhere in the segment but not in the quote', () => {
    const refs = sanitizeReferences(
      [
        { kind: 'book', name: 'The Sovereign Individual', role: 'recommends' },
        { kind: 'app', name: 'Cursor', role: 'uses' },
      ],
      'I still recommend The Sovereign Individual.'
    );
    expect(refs).toEqual([{ kind: 'book', name: 'The Sovereign Individual', role: 'recommends' }]);
  });

  it('drops mentions and roles supported only by a different clause', () => {
    const refs = sanitizeReferences(
      [
        { kind: 'book', name: 'The Sovereign Individual', role: 'mentions' },
        { kind: 'book', name: 'The Sovereign Individual', role: 'uses' },
        { kind: 'app', name: 'Cursor', role: 'recommends' },
      ],
      segment
    );
    expect(refs).toEqual([]);
  });

  it('keeps built, avoids, and reading speech acts', () => {
    const refs = sanitizeReferences(
      [
        { kind: 'tool', name: 'comma.ai', role: 'built' },
        { kind: 'service', name: 'Facebook', role: 'avoids' },
        { kind: 'book', name: 'The Beginning of Infinity', role: 'uses' },
      ],
      'I built comma.ai from scratch. I do not use Facebook anymore. I am reading The Beginning of Infinity this week.'
    );
    expect(refs.map(({ name, role }) => [name, role])).toEqual([
      ['comma.ai', 'built'],
      ['Facebook', 'avoids'],
      ['The Beginning of Infinity', 'uses'],
    ]);
  });

  it('keeps contracted reading and past-tense book preferences', () => {
    expect(
      sanitizeReferences(
        [
          { kind: 'book', name: 'The Beginning of Infinity', role: 'uses' },
          { kind: 'book', name: 'How to Raise an Adult', role: 'likes' },
        ],
        "I've read The Beginning of Infinity three times. One book I really liked was How to Raise an Adult."
      )
    ).toEqual([
      { kind: 'book', name: 'The Beginning of Infinity', role: 'uses' },
      { kind: 'book', name: 'How to Raise an Adult', role: 'likes' },
    ]);
  });

  it('keeps title-first reading, positive book evaluation, and deictic recommendation', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'The Gruffalo', role: 'uses' }],
        "There's one called The Gruffalo, I read to my kids every night before bed."
      )
    ).toEqual([{ kind: 'book', name: 'The Gruffalo', role: 'uses' }]);
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'Functional Programming in Scala', role: 'likes' }],
        'Functional Programming in Scala is the single best technical book I have ever read.'
      )
    ).toEqual([{ kind: 'book', name: 'Functional Programming in Scala', role: 'likes' }]);
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'The Upside of Stress', role: 'recommends' }],
        'The Upside of Stress changed how I approach hard work, and I highly recommend it.'
      )
    ).toEqual([{ kind: 'book', name: 'The Upside of Stress', role: 'recommends' }]);
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'Design of Everyday Things', role: 'likes' }],
        "I do love the Design of Everyday Things. I think that's such a classic."
      )
    ).toEqual([{ kind: 'book', name: 'Design of Everyday Things', role: 'likes' }]);
  });

  it('accepts a bare enumerated title only for an audited book-answer pass', () => {
    const raw = [{ kind: 'book', name: 'The Power Broker', role: 'recommends' }] as const;
    const quote = 'The first is The Power Broker by Robert Caro, which changed how I think.';
    expect(sanitizeReferences(raw, quote)).toEqual([]);
    expect(sanitizeReferences(raw, quote, quote, true)).toEqual([
      { kind: 'book', name: 'The Power Broker', role: 'recommends' },
    ]);
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'Code', role: 'recommends' }],
        'Code by Charles Petzold explains the secret language of hardware and software.',
        undefined,
        true
      )
    ).toEqual([{ kind: 'book', name: 'Code', role: 'recommends' }]);
  });

  it('drops audited non-title labels even in a book-answer pass', () => {
    const names = [
      'Andrew Roberts latest book on Winston Churchill',
      'Elon Musk book',
      "Kim Scott's writing",
      'The How to Book',
    ];
    for (const name of names) {
      expect(
        sanitizeReferences(
          [{ kind: 'book', name, role: 'recommends' }],
          `I recommend ${name}.`,
          undefined,
          true
        )
      ).toEqual([]);
    }
  });

  it('keeps preferences and ownership distinct from recommendations', () => {
    const quote =
      "I love Linear for planning, and I bought The Staff Engineer's Path last week. These are personal choices, not blanket recommendations.";
    expect(
      sanitizeReferences(
        [
          { kind: 'app', name: 'Linear', role: 'likes' },
          { kind: 'book', name: "The Staff Engineer's Path", role: 'owns' },
          { kind: 'app', name: 'Linear', role: 'recommends' },
        ],
        quote
      )
    ).toEqual([
      { kind: 'app', name: 'Linear', role: 'likes' },
      { kind: 'book', name: "The Staff Engineer's Path", role: 'owns' },
    ]);
  });

  it('normalizes a kind that conflicts with the quoted context', () => {
    const refs = sanitizeReferences(
      [
        { kind: 'book', name: 'Zork', role: 'recommends' },
        { kind: 'other', name: 'Zork', role: 'recommends' },
      ],
      'Zork was a fantastic game, and I highly recommend Zork to everyone.'
    );
    expect(refs).toEqual([{ kind: 'other', name: 'Zork', role: 'recommends' }]);
  });

  it('normalizes an account mislabeled as an app', () => {
    const refs = sanitizeReferences(
      [
        {
          kind: 'app',
          name: 'FFmpeg account on Twitter/X',
          role: 'recommends',
        },
      ],
      'I recommend the FFmpeg account on Twitter/X to everybody who likes open source.'
    );
    expect(refs).toEqual([
      {
        kind: 'other',
        name: 'FFmpeg account on Twitter/X',
        role: 'recommends',
      },
    ]);
  });

  it('converges audited cross-kind duplicates to one public kind', () => {
    const quote = 'I use Coda every day.';
    for (const kind of ['app', 'tool'] as const) {
      expect(sanitizeReferences([{ kind, name: 'Coda', role: 'uses' }], quote)).toEqual([
        { kind: 'app', name: 'Coda', role: 'uses' },
      ]);
    }
  });

  it('rejects generic objects, passive hearsay, and people who are not the object', () => {
    const cases = [
      [
        'Anybody listening should know I highly recommend this game.',
        { kind: 'app', name: 'this game', role: 'recommends' },
      ],
      [
        'I saw WSL2 recommended for certain operations.',
        { kind: 'tool', name: 'WSL2', role: 'recommends' },
      ],
      [
        'You had conversations with Nurlan, with Adam, which I highly recommend.',
        { kind: 'person', name: 'Adam', role: 'recommends' },
      ],
      [
        'I read a paper recently about modern working scientists.',
        { kind: 'paper', name: 'a paper', role: 'uses' },
      ],
    ] as const;
    for (const [quote, reference] of cases) {
      expect(sanitizeReferences([reference], quote)).toEqual([]);
    }
  });

  it('rejects a pronoun object followed by an unrelated name', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'Crime and Punishment', role: 'uses' }],
        'I read it when they first did Crime and Punishment, and that was amazing.'
      )
    ).toEqual([]);
  });

  it('rejects descriptive phrases that are not named references', () => {
    expect(
      sanitizeReferences(
        [
          { kind: 'other', name: 'leading and suggestive questions', role: 'uses' },
          {
            kind: 'other',
            name: 'many sources who disagree with each other',
            role: 'recommends',
          },
        ],
        'I used leading and suggestive questions in my research. I recommend many sources who disagree with each other.'
      )
    ).toEqual([]);
  });

  it('rejects generic plural categories', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'books', role: 'uses' }],
        'As you can tell, I read a lot of books.'
      )
    ).toEqual([]);
  });

  it('rejects descriptive book labels and book subjects', () => {
    const cases = [
      ["I read Bill Walsh's book.", "Bill Walsh's book", 'uses'],
      ['I love John Klassen books.', 'John Klassen books', 'likes'],
      ["I use Gwern's book reviews.", "Gwern's book reviews", 'uses'],
      [
        'The front inside cover of this book is something I read every year.',
        'The front inside cover of this book',
        'uses',
      ],
      ['I read a book about Roy Cohn.', 'Roy Cohn', 'uses'],
    ] as const;
    for (const [quote, name, role] of cases) {
      expect(sanitizeReferences([{ kind: 'book', name, role }], quote)).toEqual([]);
    }
  });

  it('reclassifies audited non-book names', () => {
    const cases = [
      ['I love Hey Jude.', 'Hey Jude', 'likes', 'other'],
      ['I read Wikipedia.', 'Wikipedia', 'uses', 'other'],
      ['I love Michael Lewis.', 'Michael Lewis', 'likes', 'person'],
      ['I read ULM Fit.', 'ULM Fit', 'uses', 'paper'],
    ] as const;
    for (const [quote, name, role, kind] of cases) {
      expect(sanitizeReferences([{ kind: 'book', name, role }], quote)).toEqual([
        { kind, name, role },
      ]);
    }
  });

  it('rejects lowercase generic objects and descriptive series names', () => {
    const cases = [
      [
        'I bought the luggage first, long before they sent more luggage.',
        { kind: 'hardware', name: 'luggage', role: 'owns' },
      ],
      [
        'I highly recommend people watch your series with 3Blue1Brown on distance.',
        {
          kind: 'other',
          name: 'your series with 3Blue1Brown on distance',
          role: 'recommends',
        },
      ],
      ["I don't use AI note taking.", { kind: 'tool', name: 'AI note taking', role: 'avoids' }],
      [
        'I love how everything connects to how tech works and how AI came to be.',
        {
          kind: 'other',
          name: 'how everything connects to how tech works and how AI came to be',
          role: 'likes',
        },
      ],
      [
        'One of my favorite books is one that was sent to me by Nijolė Skripskaitė.',
        {
          kind: 'book',
          name: 'one that was sent to me by Nijolė Skripskaitė',
          role: 'likes',
        },
      ],
    ] as const;
    for (const [quote, reference] of cases) {
      expect(sanitizeReferences([reference], quote)).toEqual([]);
    }
  });

  it('normalizes an explicitly named channel or podcast to other', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'app', name: 'Animagraffs', role: 'recommends' }],
        'I highly recommend the channel, Animagraffs.'
      )
    ).toEqual([{ kind: 'other', name: 'Animagraffs', role: 'recommends' }]);
    expect(
      sanitizeReferences(
        [{ kind: 'app', name: 'Invest Like the Best', role: 'uses' }],
        'I listened to an episode of Invest Like the Best last year.'
      )
    ).toEqual([{ kind: 'other', name: 'Invest Like the Best', role: 'uses' }]);
  });

  it('rejects a topic mistaken for the recommended book title', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'the origins of Trump', role: 'recommends' }],
        'That ties in with another book I recommended to you about the origins of Trump.'
      )
    ).toEqual([]);
  });

  it('normalizes an author shorthand mislabeled as a book', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'Solzhenitsyn', role: 'uses' }],
        'I read in Solzhenitsyn that the authorities made hundreds of decisions a day.'
      )
    ).toEqual([{ kind: 'other', name: 'Solzhenitsyn', role: 'uses' }]);
  });

  it('rejects a descriptive book phrase promoted into a title', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'his new book on Elon', role: 'recommends' }],
        'I highly recommend people read his new book on Elon.'
      )
    ).toEqual([]);
  });

  it('rejects a person incidental to the recommended action', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'person', name: 'Americans', role: 'recommends' }],
        'I recommend being a POW with the Americans. That would be my choice.'
      )
    ).toEqual([]);
  });

  it('normalizes a documentary mislabeled as a book', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'This Place Rules', role: 'recommends' }],
        'He created the documentary I highly recommend called This Place Rules.'
      )
    ).toEqual([{ kind: 'other', name: 'This Place Rules', role: 'recommends' }]);
  });

  it('rejects recommended media wrapped around a person name', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'person', name: 'Serhii Plokhy', role: 'recommends' }],
        'I recommend my conversation with Serhii Plokhy about the history of the region.'
      )
    ).toEqual([]);
  });

  it("rejects a reference spoken inside someone else's reported quote", () => {
    expect(
      sanitizeReferences(
        [{ kind: 'book', name: 'Ayn Rand', role: 'uses' }],
        'A woman said this to me, “It never occurred to me that I could be a doctor until I read Ayn Rand.”'
      )
    ).toEqual([]);
    expect(
      sanitizeReferences(
        [
          {
            kind: 'book',
            name: 'In those moments of pain, you can either be broken or broken open',
            role: 'uses',
          },
        ],
        'Then I read another book, by Frederick Buechner, who said, “In those moments of pain, you can either be broken or broken open.”'
      )
    ).toEqual([]);
  });

  it('deduplicates the same named item and role across model-supplied kinds', () => {
    expect(
      sanitizeReferences(
        [
          { kind: 'app', name: 'v0', role: 'uses' },
          { kind: 'tool', name: 'v0', role: 'uses' },
        ],
        'We use v0 every day.'
      )
    ).toEqual([{ kind: 'app', name: 'v0', role: 'uses' }]);
  });

  it('uses source context outside the quote to resolve a kind conflict', () => {
    expect(
      sanitizeReferences(
        [{ kind: 'app', name: 'Zork', role: 'recommends' }],
        'I highly recommend Zork.',
        'Zork changed how I think about games. I highly recommend Zork.'
      )
    ).toEqual([{ kind: 'other', name: 'Zork', role: 'recommends' }]);
  });

  it('preserves explicit book and person recommendations in book context', () => {
    const quote =
      'She has a wide variety of best-selling children’s books, but her most recent book is Super-Infinite: The Transformations of John Donne, which I recommend very, very highly. And of course, I recommend Donne as well.';
    expect(
      sanitizeReferences(
        [
          {
            kind: 'book',
            name: 'Super-Infinite: The Transformations of John Donne',
            role: 'recommends',
          },
          { kind: 'person', name: 'Donne', role: 'recommends' },
        ],
        quote
      )
    ).toEqual([
      {
        kind: 'book',
        name: 'Super-Infinite: The Transformations of John Donne',
        role: 'recommends',
      },
      { kind: 'person', name: 'Donne', role: 'recommends' },
    ]);
  });
});

describe('referenceAssertion', () => {
  it('does not turn observed use into a recommendation', () => {
    expect(referenceAssertion({ kind: 'app', name: 'TikTok', role: 'uses' })).toBe(
      'Mentions personal use of TikTok.'
    );
  });
});

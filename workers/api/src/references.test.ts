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

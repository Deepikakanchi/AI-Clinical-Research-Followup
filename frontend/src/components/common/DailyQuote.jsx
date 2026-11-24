/*
 * components/common/DailyQuote.jsx - A short research quotation for the header.
 * Changes once a day; decorative only.
 */

const QUOTES = [
  { text: 'In the field of observation, chance favours only the prepared mind.', by: 'Louis Pasteur' },
  { text: 'Every careful observation today becomes tomorrow’s evidence.' },
  { text: 'Good research begins with good records.' },
  { text: 'Behind every data point is a person who chose to help.' },
  { text: 'Accuracy first: what is not written down did not happen.' },
  { text: 'Follow-up is where research keeps its promises.' },
  { text: 'Consent is the foundation every study is built on.' },
];

// Same quote all day; a different one each day.
function quoteOfTheDay() {
  const day = Math.floor(Date.now() / 86_400_000);
  return QUOTES[day % QUOTES.length];
}

export default function DailyQuote() {
  const q = quoteOfTheDay();
  return (
    <p className="daily-quote" title={q.by ? `“${q.text}” — ${q.by}` : `“${q.text}”`}>
      <span className="quote-mark" aria-hidden="true">“</span>
      <span className="quote-text">{q.text}</span>
      <span className="quote-mark" aria-hidden="true">”</span>
      {q.by && <span className="daily-quote-by">— {q.by}</span>}
    </p>
  );
}
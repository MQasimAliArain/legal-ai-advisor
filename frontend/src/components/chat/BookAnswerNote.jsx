import React from 'react';

export default function BookAnswerNote({ reference, disclaimer }) {
  if (!reference && !disclaimer) return null;

  return (
    <div className="mt-2.5 border-t border-slate-200 dark:border-slate-700 pt-2 text-xs space-y-1">
      {reference && (
        <div className="text-slate-700 dark:text-slate-300">
          <span className="font-semibold">Book Reference:</span> {reference}
        </div>
      )}
      {disclaimer && (
        <div className="text-slate-500 dark:text-slate-400 italic">
          {disclaimer}
        </div>
      )}
    </div>
  );
}
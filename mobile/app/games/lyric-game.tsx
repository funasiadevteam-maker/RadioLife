import React from 'react';
import QuizGame from '../../src/components/QuizGame';
import { HOUSE_CAMPAIGNS } from '../../src/api/gamesApi';

/* Guess the Lyric — games_v2 campaign `cmp_house_lyric` (tpl_quiz).
   Puzzles are drawn from the `lyric_puzzles` pool server-side. */
export default function LyricGameScreen() {
  return (
    <QuizGame
      campaignId={HOUSE_CAMPAIGNS.lyric}
      headerTitle="Guess the Lyric"
      accent="#6366F1"
      icon="mic"
      testIDPrefix="lyric"
    />
  );
}

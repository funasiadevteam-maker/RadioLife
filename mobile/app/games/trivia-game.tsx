import React from 'react';
import QuizGame from '../../src/components/QuizGame';
import { HOUSE_CAMPAIGNS } from '../../src/api/gamesApi';

/* Music Trivia — games_v2 campaign `cmp_house_trivia` (tpl_quiz).
   Questions are generated live from the station's track pool, so the
   prompt/options come straight off the session render_config. */
export default function TriviaGameScreen() {
  return (
    <QuizGame
      campaignId={HOUSE_CAMPAIGNS.trivia}
      headerTitle="Music Trivia"
      accent="#f59e0b"
      icon="musical-notes"
      testIDPrefix="trivia"
    />
  );
}

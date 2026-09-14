/* Shared by the static renderer, browser tool, and behavior checks. */
(function(root) {
  function questions(data, genre, stage, features) {
    const selectedGenre = data.genres[genre] || data.genres.general;
    const selectedStage = data.stages[stage] || data.stages.excerpt;
    return [...data.common, ...selectedGenre.questions,
      {id:'stage', question:selectedStage.question, why:selectedStage.why},
      ...features.filter(key => data.features[key]).map(key => ({id:key,...data.features[key]}))
    ].filter(item => !(stage === 'excerpt' && item.completeOnly));
  }
  if (typeof module !== 'undefined') module.exports = {questions};
  else root.ReaderfoldQuestions = {questions};
})(typeof window !== 'undefined' ? window : globalThis);

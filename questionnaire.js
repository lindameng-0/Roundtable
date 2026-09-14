(async function() {
  const tool = document.querySelector('[data-questionnaire]');
  if (!tool) return;
  const status = tool.querySelector('[role=status]');
  try {
    const response = await fetch('/questionnaire-data.json');
    if (!response.ok) throw new Error('Unavailable');
    const data = await response.json();
    const genre = tool.querySelector('[name=genre]');
    const stage = tool.querySelector('[name=stage]');
    const output = tool.querySelector('[data-questions]');
    const focus = tool.querySelector('[data-focus]');
    let appliedGenre = genre.value, appliedStage = stage.value;
    const selectedFeatures = () => Array.from(tool.querySelectorAll('[name=feature]:checked')).map(input => input.value);
    function render() {
      appliedGenre = genre.value; appliedStage = stage.value;
      const items = window.ReaderfoldQuestions.questions(data, genre.value, stage.value, selectedFeatures());
      output.replaceChildren(...items.map(item => {
        const li = document.createElement('li');
        const label = document.createElement('label');
        const check = document.createElement('input'); check.type = 'checkbox'; check.checked = true;
        check.dataset.include = item.id; check.setAttribute('aria-label', 'Include question: '+item.question);
        const textarea = document.createElement('textarea'); textarea.value = item.question;
        textarea.setAttribute('aria-label','Edit question: '+item.question); textarea.rows=3; textarea.maxLength=700;
        const why = document.createElement('small'); why.textContent=item.why;
        label.append(check, document.createTextNode(' Include')); li.append(label,textarea,why); return li;
      }));
      focus.textContent = data.genres[genre.value].focus;
      status.textContent = items.length+' questions ready. Edit or uncheck any before downloading. Changing the options resets your edits.';
    }
    tool.querySelector('[data-build]').addEventListener('click',render);
    const text = () => 'Readerfold '+data.genres[appliedGenre].label+' beta reader questionnaire\n'+data.stages[appliedStage].label+'\n\nPlease give a chapter or passage with each answer. Skip questions that do not apply.\n\n'+Array.from(output.children).filter(li => li.querySelector('[data-include]').checked).map((li,i)=>(i+1)+'. '+li.querySelector('textarea').value).join('\n\n')+'\n\nSource: '+location.origin+location.pathname+'\n';
    tool.querySelector('[data-download]').addEventListener('click',() => {
      if(!output.querySelector('[data-include]:checked')) {status.textContent='Select at least one question to download.';return;}
      const url=URL.createObjectURL(new Blob([text()],{type:'text/plain;charset=utf-8'}));
      const a=document.createElement('a');a.href=url;a.download='readerfold-'+appliedGenre+'-questions.txt';a.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='Your editable questionnaire is ready to save.';
    });
    tool.querySelector('[data-copy-focus]').addEventListener('click',async()=>{
      try {await navigator.clipboard.writeText(focus.textContent);status.textContent='Reading focus copied.';}
      catch {status.textContent='Copy the reading focus shown below manually.';}
    });
    tool.querySelector('[data-use-focus]').addEventListener('click',()=>{
      try {localStorage.setItem('readerfold.readingFocus',JSON.stringify({note:focus.textContent,genre:appliedGenre,createdAt:Date.now()}));}
      catch { /* The signup link remains available; the focus can be copied. */ }
    });
    tool.querySelectorAll('button,select,input').forEach(el=>el.disabled=false);
    render();
  } catch {status.textContent='The customizer could not load. The questions below are still available to read or print. Reload to try again.';}
})();

var support_voice = 1;
if (!('webkitSpeechRecognition' in window)) {
  support_voice = 0;
} else {
  var recognition = new webkitSpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  recognition.onstart = function() {
    document.getElementById("voice").style.visibility = "hidden";
    document.getElementById("recording").style.visibility = "visible";
  }

  recognition.onresult = function(event) {
    var interim_transcript = '';
    if (typeof(event.results) == 'undefined') {
        recognition.onend = null;
        recognition.stop();
        return;
    }
    for (var i = event.resultIndex; i < event.results.length; ++i) {
        interim_transcript += event.results[i][0].transcript;
    }
    document.getElementById('question').value = interim_transcript;
  }

  recognition.onend = function() {
    document.getElementById("recording").style.visibility = "hidden";
    document.getElementById("voice").style.visibility = "visible";

  }
}

function startButton(event) {
  if(support_voice == 1){
    recognition.start();
  }else{
    voice_msg = String.raw`<div class="msg_window"> <img src="/static/lion1.png" alt="Avatar"><p>Currently, speech recognition does not supports this browser. Please update it or try other browsers</p></div>`;
    $( "#ans" ).append(voice_msg);
    var scroll = document.getElementById('ans');
    scroll.scrollTop = scroll.scrollHeight;
  }
}
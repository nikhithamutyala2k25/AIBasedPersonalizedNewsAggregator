const voiceButton = document.getElementById("voice-summarize-btn");

if (voiceButton) {
    const speech = new SpeechSynthesisUtterance();
    let isSpeaking = false;

    voiceButton.addEventListener("click", () => {
        if (isSpeaking) {
            window.speechSynthesis.cancel();
            isSpeaking = false;
            voiceButton.innerText = "Voice Activated Summaries";
            return;
        }

        const headlines = document.querySelectorAll("h3");
        const summaries = document.querySelectorAll("p");
        let textToSpeak = "";

        headlines.forEach((headline, index) => {
            textToSpeak += `Headline: ${headline.innerText}. Summary: ${summaries[index].innerText}. `;
        });

        speech.text = textToSpeak;
        window.speechSynthesis.speak(speech);
        isSpeaking = true;
        voiceButton.innerText = "Stop Summarizing";
    });
}

const bookmarkArticle = (title, url) => {
    fetch('/bookmark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, url })
    }).then(() => {
        alert("Article bookmarked!");
    }).catch(err => {
        console.error("Error bookmarking article:", err);
    });
};

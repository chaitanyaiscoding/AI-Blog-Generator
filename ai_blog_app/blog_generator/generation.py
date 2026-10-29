import os
import tempfile
from functools import cache
from pathlib import Path

import whisper
import yt_dlp
from openai import OpenAI


# OPENAI_API_KEY comes from .env, which settings.py loads into os.environ at startup.
@cache
def get_openai_client():
    return OpenAI(api_key=os.environ['OPENAI_API_KEY'])


def generate_article(transcript):
    response = get_openai_client().chat.completions.create(
        model='gpt-4o-mini',
        messages=[
            {
                'role': 'system',
                'content': 'You are a writer who turns video transcripts into clear, engaging blog articles.',
            },
            {
                'role': 'user',
                'content': (
                    'Write a blog article of about 200 words based on the following YouTube video transcript. '
                    'Write it as a standalone article, not as a description of a video.\n\n'
                    f'Transcript:\n{transcript}'
                ),
            },
        ],
    )
    return response.choices[0].message.content

# Loading the model takes a few seconds, so load it on first use and reuse it after that.
# "base" is a good speed/accuracy tradeoff on CPU; try "small" for better accuracy.
@cache
def get_whisper_model():
    return whisper.load_model("base")


# Downloads only the audio track into out_dir and returns (video title, path to the audio file).
def download_audio(url, out_dir):
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(Path(out_dir) / '%(id)s.%(ext)s'),
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info['title'], ydl.prepare_filename(info)


def get_transcript(audio_path):
    # fp16=False avoids the "FP16 is not supported on CPU" warning.
    result = get_whisper_model().transcribe(audio_path, fp16=False)
    return result['text']


def generate_blog_content(url):
    # The temp dir (and the audio file in it) is deleted when the block exits.
    with tempfile.TemporaryDirectory() as tmp:
        title, audio_path = download_audio(url, tmp)
        transcript = get_transcript(audio_path)

    return generate_article(transcript)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# A short script to that wraps the DeepSpeech phoneme recognition system to
# act as a local recognizer in ELAN.
#

import os
import os.path

logfile = "/Users/npartane/github/DeepSpeech-test/log.txt"

if os.path.exists(logfile):
    os.remove(logfile)

f = open(logfile, "a")
f.write("Starting\n")

import atexit
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

from deepspeech import Model
import numpy as np
import wave
from pathlib import Path

import pydub

f.write("imports ok\n")

# The set of annotations (dicts) parsed out of the given ELAN tier.
annotations = []

# The parameters provided by the user via the ELAN recognizer interface
# (specified in CMDI).
params = {}

f.write("looking for ffmpeg\n")

# Begin by tracking down the ffmpeg(1) executable that this recognizer will use
# to process audio materials.  If ffmpeg(1) doesn't exist in the current path, 
# exit now to save everyone some heartbreak later on.
ffmpeg = shutil.which('ffmpeg')
if not ffmpeg:
    sys.exit(-1)

f.write("ffmpeg ok (skipped testing)\n")

# Read in all of the parameters that ELAN passes to this local recognizer on
# standard input.
for line in sys.stdin:
    match = re.search(r'<param name="(.*?)".*?>(.*?)</param>', line)
    if match:
        params[match.group(1)] = match.group(2).strip()

f.write('passed parameter check\n')

for i in params:

    f.write(f"{i, params[i]}\n")

# With those parameters in hand, grab the 'input_tier' parameter, open that
# XML document, and read in all of the annotation start times, end times,
# and values.
print("PROGRESS: 0.1 Loading annotations on input tier", flush = True)
with open(params['input_tier'], 'r', encoding = 'utf-8') as input_tier:
    for line in input_tier:
        match = re.search(r'<span start="(.*?)" end="(.*?)"><v>(.*?)</v>', line)
        if match:
            annotation = { \
                'start': int(float(match.group(1)) * 1000.0), \
                'end' : int(float(match.group(2)) * 1000.0), \
                'value' : match.group(3) }
            annotations.append(annotation)

f.write('Managed to process the xml.\n')

# Then use ffmpeg(1) to convert the 'source' audio file into a temporary 16-bit
# mono 16KHz WAV, then load that temp file into pydub for easier exporting of
# audio clips in the format that Persephone expects. 
print("PROGRESS: 0.2 Converting source audio", flush = True)
converted_audio_file = tempfile.NamedTemporaryFile(suffix = '.wav')
subprocess.call([ffmpeg, '-y', '-v', '0', \
    '-i', params['source'], \
    '-ac', '1',
    '-ar', '16000',
    '-sample_fmt', 's16',
    '-acodec', 'pcm_s16le', \
    converted_audio_file.name])
converted_audio = pydub.AudioSegment.from_file(converted_audio_file, \
    format = 'wav')

f.write("Converted audio\n")

# Create a set of WAV clips for each of the annotations specified in
# 'input_tier' in the format that DeepSpeech expects, storing them under
# temporary names in the 'wav' directory under the given corpus data
# directory and making a list of their names (without the file extensions)
# in 'untranscribed_prefixes.txt'.
#
# (When we reload the existing training corpus with these temporary audio
#  clips saved in 'wav', Persephone will copy (and convert, if needed) each
#  clip to 'feat', creating the necessary '.npy' files along the way.  We
#  still need to create 'untranscribed_prefixes.txt' by hand (and, later, move
#  the new clips and .npy files into 'feat/untranscribed/', while keeping
#  copies in 'wav' at least until we've reloaded the corpus -- Persephone
#  won't recognize them as untranscribed unless they're in both 'wav' *and*
#  'feat/untranscribed'), but that's not  hard to do.



print("PROGRESS: 0.3 Creating temporary clips", flush = True)

#prefix_to_annotation = {}

untranscribed_dir = os.path.join(params['corpus_dir'], 'wav')

for annotation in annotations:

    # Save the audio clip in a named temporary file in the corpus 'feat/
    # untranscribed' directory. 
    annotation['clip'] = tempfile.NamedTemporaryFile(suffix = '.wav', \
        dir = untranscribed_dir)
    f.write(f"{annotation}")
    clip = converted_audio[annotation['start']:annotation['end']]
    clip.export(annotation['clip'], format = 'wav')

    # Map from this prefix to the corresponding annotation (for quick
    # lookups later on when parsing out recognized text)
#    prefix_to_annotation[annotation['clip_prefix']] = annotation

# Now that clips in the appropriate format have been created, close (and
# thereby delete) the temporary converted source recording.  This isn't
# strictly necessary, but it doesn't hurt.
converted_audio_file.close()

f.write(f'\n\nGot to this part…\n')

# Now prepare input features for all of the clips in 'feat/untranscribed'.
# Having these features in place before loading the corpus convinces
# Persephone that it doesn't need to reprocess the entire corpus, lowering
# the overall time required for transcription.
##print("PROGRESS: 0.4 Extracting features from clips", flush = True)
##persephone.preprocess.feat_extract.from_dir(untranscribed_dir, \
##    params['feat_type'])


# Now that all of the clips and '.npy' files are where they need to be for
# Persephone to find them and an 'untranscribed_prefixes.txt' file is in place,
# load the corpus.  Persephone should now find all of these files and know to
# treat them as untranscribed segments.
##print("PROGRESS: 0.6 Loading corpus into Persephone", flush = True)
##corp = persephone.corpus.Corpus(feat_type = params['feat_type'], \
##    label_type = params['label_type'], tgt_dir = params['corpus_dir'])

# Then load the Persephone model specified in the 'persephone_model' parameter,
# then use it to start transcribing the clips created above (ideally reporting
# our progress via messages on stdout, though that doesn't look to be possible
# here with the current API.  Sigh...)
print("PROGRESS: 0.7 Creating temporary experiment directory", flush = True)
temp_dir = tempfile.TemporaryDirectory()

ds = Model("/Users/npartane/github/DeepSpeech-test/deepspeech-0.6.1-models/output_graph.pbmm", 500)

f.write("\n\nloaded DeepSpeech model\n\n")

for annotation in annotations:

    fin = wave.open(annotation['clip'].name, 'rb')
    f.write("\n\nread temp file\n\n")
    audio = np.frombuffer(fin.readframes(fin.getnframes()), np.int16)
    f.write("\n\ntrying to save the result\n\n")
    annotation['value'] = (ds.stt(audio))

#new_experiment_dir = persephone.experiment.prep_exp_dir(temp_dir.name)

##print("PROGRESS: 0.8 Creating Persephone model", flush = True)
##corp_reader = persephone.corpus_reader.CorpusReader(corp, \
##    num_train = model_parameters['num_train'], \
##    batch_size = model_parameters['batch_size'])

#model = persephone.rnn_ctc.Model(new_experiment_dir, corp_reader, \
##    num_layers = model_parameters['num_layers'], \
##    hidden_size = model_parameters['hidden_size'])

# 'exp_dir' (e.g., '5') - experiment dir of trained model to apply
# /Users/chris/Desktop/CURRENT-PROJECTS/Persephone/persephone-tutorial/exp/5
##print("PROGRESS: 0.9 Transcribing clips", flush = True)
##model.transcribe(os.path.join(params['exp_dir'], 'model', 'model_best.ckpt'))

# Now that transcription is finished, we can open 'EXPERIMENT_DIR/
# transcriptions/hyps.txt' and parse out the phoneme strings, storing them
# under the corresponding annotation.
##with open(os.path.join(new_experiment_dir, 'transcriptions', 'hyps.txt'), \
##    'r', encoding = 'utf-8') as recognized_text_file:
##    while True:
##        # Read the file in three-line blocks.
##        prefix = recognized_text_file.readline()
##        if not prefix:
##            break
##
##        # Strip off the path and '.{FEAT}.npy' file extensions to get back
##        # to a usable prefix.
##        prefix = os.path.basename(prefix)
##        prefix = prefix[:prefix.index('.')]
##
##        text = recognized_text_file.readline()
##        recognized_text_file.readline()  # skip empty third line
##
##        # Find the corresponding annotation and stores the recognized text
##        # in it under 'value'.
##        annotation = prefix_to_annotation[prefix]
##        annotation['value'] = text.strip()

# Then open 'output_tier' for writing, and return all of the new phoneme
# strings produced by Persephone as the contents of <span> elements (see
# below).
print("PROGRESS: 0.95 Preparing output tier", flush = True)

f.write(f"\n\nStarting to save tiers\n")

with open(params['output_tier'], 'w', encoding = 'utf-8') as output_tier:
    # Write document header.

    output_tier.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    output_tier.write('<TIER xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="file:avatech-tier.xsd" columns="PersephoneOutput">\n')

    # Write out annotations and recognized text (e.g., '<span start="17.492"
    # end="18.492"><v>OUTPUT</v></span>').  If we've been asked to, convert
    # from Persephone's phoneme strings back into the given language's
    # orthography.
    for annotation in annotations:
        output_tier.write(\
            '    <span start="%s" end="%s"><v>%s</v></span>\n' %\
            (annotation['start'], annotation['end'], annotation['value']))

    output_tier.write('</TIER>\n')

# Finally, tell ELAN that we're done.
print('RESULT: DONE.', flush = True)

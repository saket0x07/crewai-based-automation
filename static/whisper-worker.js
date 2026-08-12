import { pipeline, env } from 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.14.0';

env.allowLocalModels = false; // We are fetching from HF Hub

class MyTranscriptionPipeline {
    static task = 'automatic-speech-recognition';
    static model = 'Xenova/whisper-base.en';
    static instance = null;

    static async getInstance(progress_callback = null) {
        if (this.instance === null) {
            this.instance = await pipeline(this.task, this.model, { progress_callback });
        }
        return this.instance;
    }
}

// Listen for messages from the main thread
self.addEventListener('message', async (event) => {
    const { type, audio, isFinal } = event.data;

    if (type === 'transcribe') {
        try {
            // Get or load the pipeline
            const transcriber = await MyTranscriptionPipeline.getInstance((x) => {
                // Send progress updates (e.g. downloading model)
                self.postMessage({ type: 'progress', data: x });
            });

            // Perform transcription
            // The audio must be a Float32Array sampled at 16000 Hz
            const output = await transcriber(audio, {
                chunk_length_s: 30,
                stride_length_s: 5,
                // Removed language parameter for .en models to prevent hallucinations
                return_timestamps: false
            });

            // Send back the result
            self.postMessage({
                type: 'result',
                text: output.text,
                isFinal: isFinal
            });
            
        } catch (error) {
            console.error('Transcription error:', error);
            self.postMessage({ type: 'error', error: error.message });
        }
    }
});

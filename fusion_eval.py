# Import necessary libraries and modules
import os
import json
import torch
from torch import nn
from PIL import Image
import functools
import numpy as np
import librosa
from torch.autograd import Variable
from opts import parse_opts
from model import generate_model
from models.fusion5 import MultiModalCNN
import transforms
from preprocess_input import extract_faces,extract_audios
import time
import warnings
from transformers import logging as transformers_logging


# Optionally, suppress all warnings from the transformers library
transformers_logging.set_verbosity_error()


def video_loader(video_dir_path):
    if not os.path.exists(video_dir_path):
        raise FileNotFoundError(f"The video file {video_dir_path} does not exist.")
    video = np.load(video_dir_path)  
    video_data = []
    for i in range(np.shape(video)[0]):
        video_data.append(Image.fromarray(video[i,:,:,:]))   
    return video_data

def get_default_video_loader():
    return functools.partial(video_loader)

def load_audio(audiofile):
    y, sr = librosa.load(audiofile, sr=22050)
    return y, sr


def get_mfccs(y, sr):
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=10)
    return mfcc

def input(data_type,video_path,audio_path,spatial_transform=None, audio_transform=None):
    loader = get_default_video_loader()       
    path = video_path
    clip = loader(path)

    if data_type == 'video' or data_type == 'audiovisual':        
        if spatial_transform is not None:               
            spatial_transform.randomize_parameters()
            clip = [spatial_transform(img) for img in clip]  

        clip = torch.stack(clip, 0).permute(1, 0, 2, 3)
                
        if data_type == 'video':
            return clip
                
    if data_type == 'audio' or data_type == 'audiovisual':
            path = audio_path

            y, sr = load_audio(path) 
            
            if audio_transform is not None:
                  audio_transform.randomize_parameters()
                  y = audio_transform(y)     
                 
            mfcc = get_mfccs(y, sr)            
            audio_features = mfcc 

            if data_type == 'audio':
                return audio_features
            
    if data_type == 'audiovisual':
            return audio_features, clip

def getinput(video_path, audio_path, modality='both'):
    
    input_video_path = video_path # Replace with your video path
    input_audio_path = audio_path

    video_transform = transforms.Compose([
                transforms.ToTensor(255)])
    
    inputs_audio,inputs_visual = input('audiovisual', input_video_path, input_audio_path, video_transform)
    modality = 'both'
    if modality == 'audio':
            print('Skipping video modality')
            if dist == 'noise':
                print('Evaluating with full noise')
                inputs_visual = torch.randn(inputs_visual.size())
            elif dist == 'addnoise': #opt.mask == -4:
                print('Evaluating with noise')
                inputs_visual = inputs_visual + (torch.mean(inputs_visual) + torch.std(inputs_visual)*torch.randn(inputs_visual.size()))
            elif dist == 'zeros':
                inputs_visual = torch.zeros(inputs_visual.size())
            else:
                print('UNKNOWN DIST!')
    elif modality == 'video':
            print('Skipping audio modality')
            if dist == 'noise':
                print('Evaluating with noise')
                inputs_audio = torch.randn(inputs_audio.size())
            elif dist == 'addnoise': #opt.mask == -4:
                print('Evaluating with added noise')
                inputs_audio = inputs_audio + (torch.mean(inputs_audio) + torch.std(inputs_audio)*torch.randn(inputs_audio.size()))

            elif dist == 'zeros':
                inputs_audio = torch.zeros(inputs_audio.size())
    a = []
    a.append(inputs_visual)
    a = torch.stack(a, dim=0)
    inputs_visual = a
    #inputs_visual = inputs_visual.unsqueeze(0)
    #inputs_visual = inputs_visual.repeat(8, 1, 1, 1, 1)
    inputs_visual = inputs_visual.permute(0,2,1,3,4)
    inputs_visual = inputs_visual.reshape(inputs_visual.shape[0]*inputs_visual.shape[1], inputs_visual.shape[2], inputs_visual.shape[3], inputs_visual.shape[4])
    inputs_audio = np.array([inputs_audio])
    inputs_audio = torch.tensor(inputs_audio)
    #inputs_audio = np.array([inputs_audio,inputs_audio,inputs_audio,inputs_audio,inputs_audio,inputs_audio,inputs_audio,inputs_audio])
    with torch.no_grad():
        inputs_visual = Variable(inputs_visual)
        inputs_audio = Variable(inputs_audio)

    return  inputs_audio,inputs_visual   

def print_emotion(output_tensor):
    emotions = ["Neutral", "Calm", "Happy", "Sad", "Angry", "Fearful", "Disgust", "Surprised"]

    # Use softmax to convert tensor values to probabilities
    probabilities = torch.softmax(output_tensor, dim=1)

    # Get the index of the maximum probability
    max_index = torch.argmax(probabilities, dim=1).item()

    # Print the corresponding emotion
    print(f"Predicted Emotion: {emotions[max_index]}")



def predict(video_name):
        # Parse command-line options
    opt = parse_opts()

    pretrained = opt.pretrain_path != 'None' 

    # Set the device to 'cuda' if available, otherwise use 'cpu'
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    # Create a directory to store results if it doesn't exist
    if not os.path.exists(opt.result_path):
        os.makedirs(opt.result_path)


    
    video_transform = transforms.Compose([
                transforms.ToTensor(opt.video_norm_value)])
    
    # Generate the model and its parameters
    torch.manual_seed(opt.manual_seed)
    #model1, parameters = generate_model(opt)

    
    fold = 1

    model = MultiModalCNN()
    model.to('cuda')
    model.load_state_dict(torch.load('./weights/model5 - Copy.pth'))


    # Load a single input video (you can replace this with your specific input path)
    video_audio_paths = [
            (f'./Examples/{video_name}.npy',f'./Examples/{video_name}.wav')
        
    ]
    start_time = time.time()
    extract_faces.extract_faces(video_name)
    end_time = time.time()  # End the timer
    elapsed_time = end_time - start_time  # Calculate elapsed time
        
    print("Extraction of faces took {:.4f} seconds".format(elapsed_time))
        
    extract_audios.extract_audios(video_name)

    # Loop over each pair of video and audio paths
    for video_path, audio_path in video_audio_paths:
        # Load the model and perform other initializations here if necessary
        

        # Load a single input video and audio
        audio, clip = getinput(video_path, audio_path, modality='both')

        # Set the model to evaluation mode
        model.eval()

        # Perform inference
        with torch.no_grad():
            output = model(f'./Examples/{video_name}.wav', clip)

        print(output.data)

        print_emotion(output.data)


predict('original')
#print(tqdm.__version__)
#print(torch.__version__)
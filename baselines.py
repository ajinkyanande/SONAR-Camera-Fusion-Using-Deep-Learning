import torch
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm
import os

device = 'cuda' if torch.cuda.is_available() else 'cpu'

class ImageClassifier(torch.nn.Module):

    def __init__(self, num_classes=5):
        super().__init__()
        
        self.net=nn.Sequential(nn.Conv2d(3,32,3,2),
                               nn.BatchNorm2d(32),
                               nn.ReLU(),
                               nn.Dropout(p=0.2),
                               nn.Conv2d(32,64,2,2),
                               nn.BatchNorm2d(64),
                               nn.ReLU(),
                               nn.Dropout(p=0.2),
                               nn.Conv2d(64,64,2,2),
                               nn.BatchNorm2d(64),
                               nn.ReLU(),
                               nn.Dropout(p=0.2),
                               nn.Conv2d(64,64,2,2),
                               nn.BatchNorm2d(64),
                               nn.ReLU(),
                               torch.nn.Flatten(),
                               nn.Linear(61504,512))

        self.cls_layer = torch.nn.Linear(512,num_classes)
        
        
    
    def forward(self, x, return_feats=False):

        feats=self.net(x)
        out=self.cls_layer(feats)
        return out
    
def train(model, camera_dataloader,sonar_dataloader, optimizer, criterion,mode="camera"):
    
    model.train()

    # Progress Bar 
    batch_bar = tqdm(total=len(camera_dataloader), dynamic_ncols=True, leave=False, position=0, desc='Train', ncols=5) 
    
    num_correct = 0
    total_loss = 0
    if mode=="camera":
      dataloader=camera_dataloader
    elif mode=="sonar":
      dataloader=sonar_dataloader
    else:
      dataloader=zip(camera_dataloader,sonar_dataloader)

    for i, data in enumerate(dataloader):
        
        if mode=="camera" or mode=="sonar":
          images=data[0]
          labels=data[1]
        else:
          image_camera=data[0][0]
          labels=data[0][1] #Same labels for both 
          image_sonar=data[1][0]
          images=torch.concat([image_camera,image_sonar],dim=1)
        
        optimizer.zero_grad() # Zero gradients

        images, labels = images.to(device), labels.to(device)
        
        with torch.cuda.amp.autocast(): # This implements mixed precision. Thats it! 
            outputs = model(images)
            #print(outputs.shape)
            #print(labels.shape)
            loss = criterion(outputs, labels)

        # Update no. of correct predictions & loss as we iterate
        num_correct += int((torch.argmax(outputs, axis=1) == labels).sum())
        total_loss += float(loss.item())

        # tqdm lets you add some details so you can monitor training as you train.
        batch_bar.set_postfix(
            acc="{:.04f}%".format(100 * num_correct / (8*(i + 1))),
            loss="{:.04f}".format(float(total_loss / (i + 1))),
            num_correct=num_correct,
            lr="{:.04f}".format(float(optimizer.param_groups[0]['lr'])))
        
        loss.backward()
        optimizer.step()

        # TODO? Depending on your choice of scheduler,
        # You may want to call some schdulers inside the train function. What are these?
      
        batch_bar.update() # Update tqdm bar

    batch_bar.close() # You need this to close the tqdm bar

    acc = 100 * num_correct / (8* len(camera_dataloader))
    total_loss = float(total_loss / len(camera_dataloader))

    return acc, total_loss

def validate(model, camera_dataloader, sonar_dataloader,criterion,mode="camera"):
  
    model.eval()
    batch_bar = tqdm(total=len(camera_dataloader), dynamic_ncols=True, position=0, leave=False, desc='Val', ncols=5)

    num_correct = 0.0
    total_loss = 0.0

    if mode=="camera":
      dataloader=camera_dataloader
    elif mode=="sonar":
      dataloader=sonar_dataloader
    else:
      dataloader=zip(camera_dataloader,sonar_dataloader)

    for i, data in enumerate(dataloader):
        
        if mode=="camera" or mode=="sonar":
          images=data[0]
          labels=data[1]
        else:
          image_camera=data[0][0]
          labels=data[0][1] #Same labels for both 
          image_sonar=data[1][0]
          images=torch.concat([image_camera,image_sonar],dim=1)


        # Move images to device
        images, labels = images.to(device), labels.to(device)
        
        # Get model outputs
        with torch.inference_mode():
            outputs = model(images)
            loss = criterion(outputs, labels)

        num_correct += int((torch.argmax(outputs, axis=1) == labels).sum())
        total_loss += float(loss.item())

        batch_bar.set_postfix(
            acc="{:.04f}%".format(100 * num_correct / (8*(i + 1))),
            loss="{:.04f}".format(float(total_loss / (i + 1))),
            num_correct=num_correct)
        batch_bar.update()
        
    batch_bar.close()
    acc = 100 * num_correct / (8* len(camera_dataloader))
    total_loss = float(total_loss / len(sonar_dataloader))
    return acc, total_loss


        
def train_baseline_models(train_loader_camera,train_loader_sonar,val_loader_camera,val_loader_sonar):       
    camera_model = ImageClassifier().to(device)
    sonar_model=ImageClassifier().to(device)

    print("Training camera model")
    criterion = torch.nn.CrossEntropyLoss()
    optimizer_camera=torch.optim.Adam(camera_model.parameters(), lr=1e-3)
    optimizer_sonar = torch.optim.Adam(sonar_model.parameters(), lr=1e-3)

    #Training camera model
    for epoch in range(0,30):

      train_acc, train_loss = train(sonar_model, train_loader_camera,train_loader_sonar,optimizer_camera, criterion,mode="camera")
      
      print("\nEpoch {}/{}: \nTrain Acc {:.04f}%\t Train Loss {:.04f}\t".format(
          epoch + 1,
          30,
          train_acc,
          train_loss))
      
      val_acc, val_loss = validate(sonar_model, val_loader_camera,val_loader_sonar, criterion,mode="camera")
      print("Val Acc {:.04f}%\t Val Loss {:.04f}".format(val_acc, val_loss))

    #Training sonar model 
    for epoch in range(0,30):

      train_acc, train_loss = train(sonar_model, train_loader_camera,train_loader_sonar,optimizer_sonar, criterion,mode="sonar")
      
      print("\nEpoch {}/{}: \nTrain Acc {:.04f}%\t Train Loss {:.04f}\t".format(
          epoch + 1,
          30,
          train_acc,
          train_loss))
      
      val_acc, val_loss = validate(sonar_model, val_loader_camera,val_loader_sonar, criterion,mode="sonar")
      print("Val Acc {:.04f}%\t Val Loss {:.04f}".format(val_acc, val_loss))
    
    return camera_model,sonar_model




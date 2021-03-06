# -*- coding: utf-8 -*-
"""
Created on Mon Sep  2 17:22:20 2019

@author: Administrator

Train a face identification model using VGG16
"""

import numpy as np
import pandas as pd
import torchvision
from torch.utils.data import DataLoader     
import torchvision.transforms as transforms

import copy
import time
from torch.optim import lr_scheduler
from torch import nn
from PIL import Image
from torch.utils.data import Dataset
import os

# load the image dataset you prepared using a csv file
class PicDataset(Dataset):
    """
    Build a dataset to load pictures
    """
    def __init__(self, csv_file, transform=None, crop=None):
        """
        Initialize PicDataset
        
        Parameters:
        ------------
        csv_file[str]:  table contains picture names, conditions and picture onset time.
                        This csv_file helps us connect cnn activation to brain images.
                        Please organize your information as:
                                     
                        [PICDIR]
                        stimID          condition   onset(optional) measurement(optional)
                        download/face1  face        1.1             3
                        mgh/face2.png   face        3.1             5
                        scene1.png      scene       5.1             4
        
        transform[callable function]: optional transform to be applied on a sample.
        crop[bool]:crop picture optionally by a bounding box.
                   The coordinates of bounding box for crop pictures should be measurements in csv_file.
                   The label of coordinates in csv_file should be left_coord,upper_coord,right_coord,lower_coord.
        """
        self.csv_file = pd.read_csv(csv_file, skiprows=1)
        with open(csv_file,'r') as f:
            self.picpath = f.readline().rstrip()
        self.transform = transform
        picname = np.array(self.csv_file['stimID'])
        condition = np.array(self.csv_file['condition'])
        self.picname = picname
        self.condition = condition
        self.crop = crop
        if self.crop:
            self.left = np.array(self.csv_file['left_coord'])
            self.upper = np.array(self.csv_file['upper_coord'])
            self.right = np.array(self.csv_file['right_coord'])
            self.lower = np.array(self.csv_file['lower_coord'])

    def __len__(self):
        """
        Return sample size
        """
        return self.csv_file.shape[0]
    
    def __getitem__(self, idx):
        """
        Get picture name, picture data and target of each sample
        
        Parameters:
        -----------
        idx: index of sample
        
        Returns:
        ---------
        picname: picture name
        picimg: picture data, save as a pillow instance
        target_label: target of each sample (label)
        """
        # load pictures
        target_name = np.unique(self.condition)
        picimg = Image.open(os.path.join(self.picpath, self.picname[idx])).convert('RGB')
        if self.crop:
            picimg = picimg.crop((self.left[idx],self.upper[idx],self.right[idx],self.lower[idx]))
        target_label = target_name.tolist().index(self.condition[idx])
        if self.transform:
            picimg = self.transform(picimg)
        else:
            self.transform = transforms.Compose([transforms.ToTensor()])
            picimg = self.transform(picimg)
        return picimg, target_label
        
    def get_picname(self, idx):
        """
        Get picture name and its condition (target condition)
        
        Parameters:
        -----------
        idx: index of sample
        
        Returns:
        ---------
        picname: picture name
        condition: target condition
        """
        return os.path.basename(self.picname[idx]), self.condition[idx]

def dnn_train_model(dataloaders_train, model, criterion, optimizer, num_epoches, train_method='tradition',
                    dataloaders_train_test=None, dataloaders_val_test=None):
    LOSS = []
    ACC_train_top1 = []
    # ACC_train_top5 = []
    ACC_val_top1 = []
    # ACC_val_top5 = []
    EPOCH = []

    time0 = time.time()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model.train()
    model = model.to(device)

    ### lr decay
    scheduler = lr_scheduler.StepLR(optimizer, 23, 250 ** (-1 / 3), last_epoch=-1)

    ### save the best model (best epoch and best accuracy)
    best_epoch = 0
    best_acc = 0

    for epoch in range(num_epoches):
        EPOCH.append(epoch + 1)
        print('Epoch time {}/{}'.format(epoch + 1, num_epoches))
        print('-' * 10)
        time1 = time.time()
        running_loss = 0.0

        for inputs, targets in dataloaders_train:
            inputs.requires_grad_(True)
            inputs = inputs.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            with torch.set_grad_enabled(True):
                if train_method == 'tradition':
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                elif train_method == 'inception':
                    # Google inception model
                    outputs, aux_outputs = model(inputs)
                    loss1 = criterion(outputs, targets)
                    loss2 = criterion(aux_outputs, targets)
                    loss = loss1 + 0.4 * loss2
                else:
                    raise Exception('Not Support this method yet, please contact authors for implementation.')

                _, pred = torch.max(outputs, 1)
                loss.backward()
                optimizer.step()
            # Statistics loss in every batch
            running_loss += loss.item() * inputs.size(0)

        # Caculate loss in every epoch
        epoch_loss = running_loss / len(dataloaders_train.dataset)
        print('Loss: {}\n'.format(epoch_loss))
        LOSS.append(epoch_loss)

        # Caculate ACC_train every epoch
        if dataloaders_train_test:
            model_copy = copy.deepcopy(model)
            # _, _, train_acc_top1, train_acc_top5 = dnn_test_model(dataloaders_train_test, model_copy)
            _, _, train_acc_top1 = dnn_test_model(dataloaders_train_test, model_copy)
            print('top1_acc_train: {}\n'.format(train_acc_top1))
            # print('top5_acc_train: {}\n'.format(train_acc_top5))
            ACC_train_top1.append(train_acc_top1)
            # ACC_train_top5.append(train_acc_top5)

        # Caculate ACC_val every epoch
        if dataloaders_val_test:
            model_copy = copy.deepcopy(model)
            # _, _, val_acc_top1, val_acc_top5 = dnn_test_model(dataloaders_val_test, model_copy)
            _, _, val_acc_top1 = dnn_test_model(dataloaders_val_test, model_copy)
            print('top1_acc_test: {}\n'.format(val_acc_top1))
            # print('top5_acc_test: {}\n'.format(val_acc_top5))
            ACC_val_top1.append(val_acc_top1)
            # ACC_val_top5.append(val_acc_top5)

        # print time of a epoch
        time_epoch = time.time() - time1
        print('This epoch training complete in {:.0f}m {:.0f}s'.format(time_epoch // 60, time_epoch % 60))

        ### Set lr decay, note that learning rate scheduler was expected to be called before the optimizer's update
        scheduler.step()

        ### save the best model while training
        if round(val_acc_top1, 4) > round(best_acc, 4):
            best_acc = val_acc_top1
            best_epoch = epoch
            #save the best model
            torch.save(model, '/nfs/h1/workingshop/tianjinhua/vgg_train/vgg_AW/vgg16_304_mix_bestmodel.pth')

    #### print the best validation accuray and epoch
    print("best epoch is " + str(best_epoch))
    print("best validation acc is " + str(best_acc))

    # store LOSS, ACC_train, ACC_val to a dict
    if dataloaders_train_test and dataloaders_val_test:
        # metric = zip(LOSS, ACC_train_top1, ACC_train_top5, ACC_val_top1, ACC_val_top5)
        metric = zip(LOSS, ACC_train_top1, ACC_val_top1)
        metric_dict = dict(zip(EPOCH, metric))
    else:
        metric_dict = dict(zip(EPOCH, LOSS))

    time_elapsed = time.time() - time0
    print('Training complete in {:.0f}m {:.0f}s'.format(time_elapsed // 60, time_elapsed % 60))
    return model, metric_dict

def dnn_test_model(dataloaders, model):
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model.eval()
    model = model.to(device)
    model_target = []
    # model_target_top5 = []
    actual_target = []

    with torch.no_grad():
        for i, (inputs, targets) in enumerate(dataloaders):
            inputs = inputs.to(device)
            outputs = model(inputs)
            _, outputs_label = torch.max(outputs, 1)
            # outputs_label_top5 = torch.topk(outputs, 5)

            model_target.extend(outputs_label.cpu().numpy())
            # model_target_top5.extend(outputs_label_top5[1].cpu().numpy())
            actual_target.extend(targets.numpy())

    model_target = np.array(model_target)
    # model_target_top5 = np.array(model_target_top5)
    actual_target = np.array(actual_target)

    # Caculate the top1 acc and top5 acc (exclude the top5 acc)
    test_acc_top1 = 1.0 * np.sum(model_target == actual_target) / len(actual_target)

    return model_target, actual_target, test_acc_top1


import torch
torch.cuda.empty_cache()

data_transforms = {
    'train': transforms.Compose([
		transforms.Resize((224,224)),
		transforms.RandomRotation(15),
		#transforms.RandomVerticalFlip(),
		transforms.RandomHorizontalFlip(),
		transforms.ToTensor(),
		transforms.Normalize(mean = [0.485, 0.456, 0.406],
							std = [0.229, 0.224, 0.225])]),

    'val': transforms.Compose([
        transforms.Resize((224,224)),
        #transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean = [0.485, 0.456, 0.406],
                             std = [0.229, 0.224, 0.225])])
    }

#training stimuli
picdataset_train = dnn_io.PicDataset('/nfs/h1/workingshop/tianjinhua/vgg_train/vgg_AW/mix_training.csv', transform=data_transforms['train'])
picdataloader_train = DataLoader(picdataset_train, batch_size=64, shuffle=True, num_workers=10)

#test training data using training stimuli
# notice that the label is not shuffled and no image augmentation
picdataset_train_val = dnn_io.PicDataset('/nfs/h1/workingshop/tianjinhua/vgg_train/vgg_AW/mix_training.csv', transform=data_transforms['val'])
dataloaders_train_test = DataLoader(picdataset_train_val, batch_size=16, shuffle=False, num_workers=10)

#test model performance
picdataset_test_val = dnn_io.PicDataset('/nfs/h1/workingshop/tianjinhua/vgg_train/vgg_AW/mix_validating.csv', transform=data_transforms['val'])
dataloaders_val_test = DataLoader(picdataset_test_val, batch_size=16, shuffle=False, num_workers=10)

# train model
vggface = torchvision.models.vgg16(pretrained=False)
vggface.classifier[6] = torch.nn.Linear(4096, 304, bias=True)
criterion = torch.nn.CrossEntropyLoss()  
optimizer = torch.optim.SGD(vggface.parameters(), lr=0.01, momentum=0.9, weight_decay=0.0005)

model,metric_dict = dnn_train_model(picdataloader_train,
                           vggface, 
                           criterion,
                           optimizer, 
                           90,
                           dataloaders_train_test = picdataloader_train,
                           dataloaders_val_test = dataloaders_val_test)
out_put = pd.DataFrame(metric_dict)
#out_put = pd.DataFrame(metric_dict,index = [0])
out_put.to_csv("/nfs/h1/workingshop/tianjinhua/vgg_train/vgg_AW/training_procedure_vgg16_304_90.csv",index=False,sep=',')

#torch.save(model, '/nfs/h1/workingshop/tianjinhua/vgg_train/vgg_AW/vgg_face_trained_vgg16_304_90.pth')
'''
best epoch is 61
best validation acc is 0.975328947368421
Training complete in 2061m 2s
'''
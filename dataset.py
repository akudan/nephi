#!/usr/bin/python
# encoding: utf-8

import random
import torch
from torch.utils.data import Dataset
from torch.utils.data import sampler
import torchvision.transforms as transforms
import lmdb
import six
import sys
from PIL import Image, ImageOps
import numpy as np

encoding = 'utf-8'

# This link has good tutorial for understanding data loaders for pytorch.
# https://www.reddit.com/r/MachineLearning/comments/6ado09/p_a_comprehensive_tutorial_for_image_transforms/

# Curtis Wigington's code also shows how to do this
#https://github.com/cwig/simple_hwr/blob/master/hw_dataset.py

def pad_size(img, size):
    delta_w = size[0] - img.size[0]
    delta_h = size[1] - img.size[1]
    padding = (0 , 0 , delta_w, delta_h)
    new_img = ImageOps.expand(img, padding, "white")
    return(new_img)

        
class lmdbDataset(Dataset):


    def __init__(self, root=None, transform=None, target_transform=None, binarize=False, augment=False, scale = False, dataset='READ', test = False, debug=False, scale_dim = 1.0, thresh = 1.0):

        self.env = lmdb.open(
            root,
            max_readers=1,
            readonly=True,
            lock=False,
            readahead=False,
            meminit=False)

        if not self.env:
            print('cannot creat lmdb from %s' % (root))
            sys.exit(0)

        with self.env.begin(write=False) as txn:
            if debug:
                self.nSamples = 1000
            else:
                nSamples = int(txn.get(str('num-samples').encode()))
                self.nSamples = nSamples
        
        self.scale_dim = scale_dim
        self.scale = scale
        self.augment = augment
        self.binarize = binarize
        self.transform = transform
        self.target_transform = target_transform
        self.dataset=dataset
        self.test = test
        self.debug = debug
        self.thresh = thresh

    def __len__(self):
        return self.nSamples

    def __getitem__(self, index):
        assert index <= len(self), 'index range error'
        index += 1
        with self.env.begin(write=False) as txn:
            img_key = 'image-%09d' % index
            if self.binarize:
                howe_imageKey = 'howe-image-%09d' % index
                simplebin_imageKey = 'simplebin-image-%09d' % index
            
            imgbuf = txn.get(img_key.encode())
            buf = six.BytesIO()
            buf.write(imgbuf)
            buf.seek(0)
            try:
                img = Image.open(buf).convert('L')
            except IOError:
                print('Corrupted image for %d' % index)
                return self[index + 1]
            if self.binarize:
                imgbuf = txn.get(howe_imageKey.encode())
                buf = six.BytesIO()
                buf.write(imgbuf)
                buf.seek(0)
                try:
                    img_howe = Image.open(buf).convert('L')
                except IOError:
                    print('Corrupted image for %d' % index)
                    return self[index + 1]
                imgbuf = txn.get(simplebin_imageKey.encode())
                buf = six.BytesIO()
                buf.write(imgbuf)
                buf.seek(0)
                try:
                    img_simplebin = Image.open(buf).convert('L')
                except IOError:
                    print('Corrupted image for %d' % index)
                    return self[index + 1]
            
            label_key = 'label-%09d' % index
            label = txn.get(label_key.encode()) if not self.test else ''   # Hopefully this still works with unicode
            
            file_key = 'file-%09d' % index
            file_name = str(txn.get(file_key.encode())) 

            if self.target_transform is not None:
                label = self.target_transform(label)
            if self.binarize:
                if (img.size[0] != img_howe.size[0] or img.size[1] != img_howe.size[1]):    # need to resize the howe image
                    img_howe = pad_size(img_howe, img.size)
            
            final_image = Image.merge("RGB", (img, img_howe, img_simplebin)) if self.binarize else img
            j = random.uniform(0.0,1.0)
            if self.augment and j < self.thresh:
                from grid_distortion import warp_image
                if self.dataset=='READ':
                    #                        sets. We place
                    #the control points on intervals of 26 pixels (slightly larger than
                    #the average baseline height) and perturbed the points about a
                    #normal distribution with a standard deviation of 1.7 pixels.
                    #These parameters are for images with a height of 80 pixels
                    # params chosen based on BYU Data Augmentation Paper by Wigington et al.
                    _, h = final_image.size
                    mesh_i = h / 80.0 * 26
                    std = h / 80.0 * 1.7
                    final_image = Image.fromarray(warp_image(np.array(final_image), w_mesh_interval=mesh_i, h_mesh_interval=mesh_i, w_mesh_std=std, h_mesh_std=std)) 
                else:
                    _, h = final_image.size
                    mesh_i = h / 80.0 * 26
                    std = h / 80.0 * 1.7
                    final_image = Image.fromarray(warp_image(np.array(final_image), w_mesh_interval=mesh_i, h_mesh_interval=mesh_i, w_mesh_std=std, h_mesh_std=std))

          
            
            # Randomly resize the image half the time (otherwise keep same size)
            j = random.uniform(0.0,1.0)
            if self.scale and j < self.thresh:
                
                # Log scale to sample shrinking and expanding with equal likelihood
                s = np.power(10, random.uniform(np.log10(1.0 / self.scale_dim[0]), np.log10(self.scale_dim[1])))
                w, h = final_image.size
                ar = float(w) / h
                new_h = int(round(s * h))
                new_w = int(round(ar * new_h))
                final_image = final_image.resize((new_w, new_h), resample=Image.BILINEAR)
            
            j = random.uniform(0.0,1.0)
            if self.transform is not None and j < self.thresh:
                final_image = self.transform(final_image)

            DEBUG = False #self.debug
            if DEBUG:
                print("The image has shape:")
                print(np.array(final_image).shape)
       
            return (final_image, label, file_name)


class resizeNormalize(object):

    def __init__(self, size, interpolation=Image.BILINEAR):
        self.size = size
        self.interpolation = interpolation
        self.toTensor = transforms.ToTensor()

    def __call__(self, img):
        
        # Resize image as necessary to new height, maintaining aspect ratio
        o_size = img.size
        AR = o_size[0] / float(o_size[1])
        img = img.resize((int(round(AR * self.size[1])), self.size[1]), self.interpolation)
        
        # Now pad to new width, as target width is guaranteed to be larger than width if keep aspect ratio is true
        o_size = img.size
        delta_w = self.size[0] - o_size[0]
        delta_h = self.size[1] - o_size[1]
        padding = (delta_w//2, delta_h//2, delta_w-(delta_w//2), delta_h-(delta_h//2))
        new_im = ImageOps.expand(img, padding, "white")
        
        img = self.toTensor(new_im)
        img.sub_(0.5).div_(0.5)
        
        return img


class randomSequentialSampler(sampler.Sampler):

    def __init__(self, data_source, batch_size):
        self.num_samples = len(data_source)
        self.batch_size = batch_size

    def __iter__(self):
        n_batch = len(self) // self.batch_size
        tail = len(self) % self.batch_size
        index = torch.LongTensor(len(self)).fill_(0)
        for i in range(n_batch):
            random_start = random.randint(0, len(self) - self.batch_size)
            batch_index = random_start + torch.range(0, self.batch_size - 1)
            index[i * self.batch_size:(i + 1) * self.batch_size] = batch_index
        # deal with tail
        if tail:
            random_start = random.randint(0, len(self) - self.batch_size)
            tail_index = random_start + torch.range(0, tail - 1)
            index[(i + 1) * self.batch_size:] = tail_index

        return iter(index)

    def __len__(self):
        return self.num_samples


class alignCollate(object):

    def __init__(self, imgH=80, imgW=300, keep_ratio=False, min_ratio=1):
        self.imgH = imgH
        self.imgW = imgW
        self.keep_ratio = keep_ratio
        self.min_ratio = min_ratio

    def __call__(self, batch):
        images, labels, files = zip(*batch)

        imgH = self.imgH
        imgW = self.imgW
        if self.keep_ratio:
            ratios = []
            for image in images:
                w, h = image.size  # PIL doesn't return channel number so w, h is all
                ratios.append(w / float(h))
            ratios.sort()
            max_ratio = ratios[-1]
            imgW = int(np.floor(max_ratio * imgH))
            
            #RA: I don't understand the purpose of this line, and for handwriting recognition imgW >= imgH
            #imgW = max(imgH * self.min_ratio, imgW)  # assure imgH >= imgW

        transform = resizeNormalize((imgW, imgH))
        images = [transform(image) for image in images]
        images = torch.cat([t.unsqueeze(0) for t in images], 0)   # Make sure this performs correctly with 3 channel images, it should, as it is adding a dimension for the batch and putting all the images together

        return images, labels, files

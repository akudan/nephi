from skimage.filters import threshold_sauvola
import cv2
import numpy

def binarize(image, window_size=25):
    if image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh_sauvola = threshold_sauvola(image, window_size=window_size)
    binary_sauvola = image > thresh_sauvola
    binary_sauvola = binary_sauvola.astype(int) * 255
    return binary_sauvola

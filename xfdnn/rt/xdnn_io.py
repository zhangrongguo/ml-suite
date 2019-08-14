
#!/usr/bin/env python
#
# // SPDX-License-Identifier: BSD-3-CLAUSE
#
# (C) Copyright 2018, Xilinx, Inc.
#
import os
import json
import argparse
from collections import OrderedDict
import h5py
import ntpath
import cv2
import numpy as np

from xfdnn.rt.xdnn_util import literal_eval
from ext.PyTurboJPEG import imread as _imread



class image_preprocessing(object):
  def __init__(self, resize=[], crop=[], pxlscale=[], meansub=[], chtranspose=None, chswap=None,
               plot=None):
    self.resize       = resize
    self.crop         = crop
    self.pxlscale     = pxlscale
    self.meansub      = meansub
    self.chtranspose  = chtranspose
    self.chswap       = chswap


def max_batch_size(x):
    maxb = 16
    if int(x) > maxb:
      print ("Limiting batch size to %d" % maxb)
    x = min( int(x), maxb)
    return x

def extant_file(x):
    """
    'Type' for argparse - checks that file exists but does not open.
    """
    if x == "-":
      # skip file check and allow empty string
      return ""

    if not os.path.exists(x):
        # Argparse uses the ArgumentTypeError to give a rejection message like:
        # error: argument input: x does not exist
        raise argparse.ArgumentTypeError("{0} does not exist".format(x))
    return x

def default_parser_args():
    parser = argparse.ArgumentParser(description='pyXDNN')
    parser.add_argument('--xclbin', help='.xclbin file', required=True, type=extant_file, metavar="FILE")
    parser.add_argument('--batch_sz', type=max_batch_size, default=-1, help='batch size')
    parser.add_argument('--dsp', type=int, default=28, help="xclbin's DSP array width")
    parser.add_argument('--netcfg', help='FPGA instructions generated by compiler for the network',
                        required=True, type=extant_file, metavar="FILE")
    parser.add_argument('--quantizecfg', help="Network's quantization parameters file",
                        required=True, type=extant_file, metavar="FILE")

    parser.add_argument('--net_def', help='prototxt file for caffe',
                        type=extant_file, metavar="FILE")
    parser.add_argument('--net_weights', help="caffe model file",
                        type=extant_file, metavar="FILE")
    
    parser.add_argument('--xlnxlib',
        help='FPGA xfDNN lib .so (deprecated)', type=extant_file, metavar="FILE")
    parser.add_argument('--outsz', type=int, default=1000,
        help='size of last layer\'s output blob')
    parser.add_argument('--weights',
        help="Folder path to network parameters/weights",
        required=True, type=extant_file, metavar="FILE")
    parser.add_argument('--labels',
        help='result -> labels translation file', type=extant_file, metavar="FILE")
    parser.add_argument('--golden', help='file idx -> expected label file', type=extant_file, metavar="FILE")
    parser.add_argument('--jsoncfg',
        help='json file with nets, data and PEs to use',
        type=extant_file, metavar="FILE")
    parser.add_argument('--images', nargs='*',
        help='directory or raw image files to use as input', required=True, type=extant_file, metavar="FILE")
    parser.add_argument('--scaleA', type=int, default=10000,
        help='weights scaling value')
    parser.add_argument('--scaleB', type=int, default=30,
        help='activation scaling value ')
    parser.add_argument('--img_raw_scale', type=float, default=255.0,
        help='image raw scale value ')
    parser.add_argument('--img_mean', type=int, nargs=3, default=[104.007,116.669,122.679],  # BGR for Caffe
        help='image mean values ')
    parser.add_argument('--img_input_scale', type=float, default=1.0,
        help='image input scale value ')
    parser.add_argument('--zmqpub', default=False, action='store_true',
        help='publish predictions to zmq port 5555')
    parser.add_argument('--perpetual', default=False, action='store_true',
        help='loop over input images forever')
    parser.add_argument('--PE', nargs='?', type=int, default=-1,
        help='preferred PE to run the classification on. Default is auto-select')
    parser.add_argument('--endLayerName', default="",
            help='layer name till the network should be run, helpful for debugging')
    parser.add_argument('--diffStartLayer', type=int, default=0,
            help="if 1 then we can run from any given layer ignoring the X's of first layers")
    parser.add_argument('--v2WeightsFormat', type=bool, default=False,
            help="Weights File specified as KernSizex KernSizey instead of only KernSize, supporting rectangle kernels")
    parser.add_argument('--layerName', default="",
            help='layername until which pyfpga should run, if left default, would run the entire model')
    parser.add_argument('--binaryFormatWeights', type=bool, default=False,
            help="Binary Format Weights Files")
    return parser

def default_xdnn_arg_parser_compiled(base='TF'):

  parser = argparse.ArgumentParser(description='XDLF_compiled')
  parser.add_argument("--base",         type=str, default="TF")
  parser.add_argument("--compilerjson",  type=str, default=None)
  parser.add_argument("--weights",  type=str, default=None)
  parser.add_argument("--data_format",  type=str, default='NCHW')
  parser.add_argument("--input_shape",  type=str, default=None)
  parser.add_argument("--labels",       type=str, default=None)
  parser.add_argument("--image_path",   type=str, default=None)
  parser.add_argument('--images',       type=extant_file, metavar='FILE', nargs='*', help='directory or raw image files to use as input')
  parser.add_argument("--image",        type=str, default=None)
  parser.add_argument('--batch_sz',     type=max_batch_size, default=-1, help='batch size')
  parser.add_argument("--image_transforms", nargs='+', type=str, help="""None if no
                      preprocessing is needed. <name> if using prespecified reprocessings; . list of
                      preprocesses.""")
  parser.add_argument("--val",          type=str, default=None)
  parser.add_argument("--num_batches",  type=int, default=-1)
  parser.add_argument("--batch",        type=int, default=4)
  parser.add_argument("--xclbin",       type=str, default='')
  parser.add_argument('--netcfg',       type=extant_file, metavar='FILE', help="""FPGA instructions
                      generated by compiler for the network""")
  parser.add_argument('--jsoncfg',      type=extant_file, metavar='FILE', help='json file with nets, data and PEs to use')
  parser.add_argument('--quantizecfg',  type=extant_file, metavar='FILE', help="""Network's
                      quantization parameters file""")
  parser.add_argument('--outsz',        type=int, default=1000, help='size of last layer\'s output blob')
  parser.add_argument('--datadir',      type=extant_file, metavar='FILE', help='Folder path to network parameters/weights')
  parser.add_argument("--xdnnv3",       action='store_true', default=False)
  parser.add_argument("--usedeephi",       action='store_true', default=False)
  parser.add_argument("--device",       type=str, default='CPU')
  parser.add_argument("--quant_cfgfile", type=str, default=None)
  parser.add_argument("--quant_recipe", type=str, default=None)
  parser.add_argument("--fpga_recipe",  type=str, default=None)
  parser.add_argument("--save",         type=str, default=None)
  parser.add_argument("--verify_dir",   type=str, default=None)
  parser.add_argument('--save2modeldir', action='store_true', default=False, help="""store network
                      partitions and compiler outpults at model directory (not at script's
                      directory.)""")

  parser.add_argument('--scaleA',       type=int, default=10000, help='weights scaling value')
  parser.add_argument('--scaleB',       type=int, default=30, help='activation scaling value ')
  parser.add_argument('--img_raw_scale',type=float, default=255.0, help='image raw scale value ')
  parser.add_argument('--img_mean',     type=int, nargs=3, default=[104.007,116.669,122.679],  # BGR for Caffe
                      help='image mean values ')
  parser.add_argument('--img_input_scale', type=float, default=1.0, help='image input scale value ')
  parser.add_argument('--zmqpub',       action='store_true', default=False, help='publish predictions to zmq port 5555')
  parser.add_argument('--perpetual',    action='store_true', default=False, help='loop over input images forever')
  parser.add_argument('--PE',           type=int, nargs='?', default=-1, help='preferred PE to run the classification on. Default is auto-select')
  parser.add_argument('--endLayerName', type=str, default='', help='layer name till the network should be run, helpful for debugging')
  parser.add_argument('--diffStartLayer',  type=int, default=0, help="if 1 then we can run from any given layer ignoring the X's of first layers")
  parser.add_argument('--v2WeightsFormat', action='store_true', default=False, help="Weights File specified as KernSizex KernSizey instead of only KernSize, supporting rectangle kernels")
  parser.add_argument('--layerName',    type=str, default='', help='layername until which pyfpga should run, if left default, would run the entire model')
  parser.add_argument('--binaryFormatWeights', action='store_true', default=False, help="Binary Format Weights Files")

  return parser

def default_xdnn_arg_parser(base='TF'):
  if base.lower() == 'tf':
    ## FIXME: Hack to by pass caffe and tensorflow co-existance issues
    from xfdnn.tools.compile.bin.xfdnn_compiler_tensorflow import default_compiler_arg_parser as default_TF_compiler_arg_parser
    parser = default_TF_compiler_arg_parser()
  elif base.lower() == 'caffe':
    ## FIXME: Hack to by pass caffe and tensorflow co-existance issues
    from xfdnn.tools.compile.bin.xfdnn_compiler_caffe import default_compiler_arg_parser as default_CAFFE_compiler_arg_parser
    parser = default_CAFFE_compiler_arg_parser()
  else:
    raise AttributeError('unsupported paltform')

  parser.add_argument("--base",         type=str, default="TF")
  parser.add_argument("--data_format",  type=str, default='NCHW')
  parser.add_argument("--input_shape",  type=str, default=None)
  parser.add_argument('--golden',       type=extant_file, metavar='FILE', help='file idx -> expected label file')
  parser.add_argument("--labels",       type=str, default=None)
  parser.add_argument("--image_path",   type=str, default=None)
  parser.add_argument('--images',       type=extant_file, metavar='FILE', nargs='*', help='directory or raw image files to use as input')
  parser.add_argument("--image",        type=str, default=None)
  parser.add_argument('--batch_sz',     type=max_batch_size, default=-1, help='batch size')
  parser.add_argument("--image_transforms", nargs='+', type=str, help="""None if no
                      preprocessing is needed. <name> if using prespecified reprocessings; . list of
                      preprocesses.""")
  parser.add_argument("--val",          type=str, default=None)
  parser.add_argument("--num_batches",  type=int, default=-1)
  parser.add_argument("--batch",        type=int, default=4)
  parser.add_argument("--xclbin",       type=str, default='')
  parser.add_argument('--netcfg',       type=extant_file, metavar='FILE', help="""FPGA instructions
                      generated by compiler for the network""")
  parser.add_argument('--jsoncfg',      type=extant_file, metavar='FILE', help='json file with nets, data and PEs to use')
  parser.add_argument('--quantizecfg',  type=extant_file, metavar='FILE', help="""Network's
                      quantization parameters file""")
  parser.add_argument('--outsz',        type=int, default=1000, help='size of last layer\'s output blob')
  parser.add_argument('--datadir',      type=extant_file, metavar='FILE', help='Folder path to network parameters/weights')
  parser.add_argument("--xdnnv3",       action='store_true', default=False)
  parser.add_argument("--device",       type=str, default='CPU')
  parser.add_argument("--quant_recipe", type=str, default=None)
  parser.add_argument("--fpga_recipe",  type=str, default=None)
  parser.add_argument("--save",         type=str, default=None)
  parser.add_argument("--verify_dir",   type=str, default=None)
  parser.add_argument('--save2modeldir', action='store_true', default=False, help="""store network
                      partitions and compiler outpults at model directory (not at script's
                      directory.)""")

  parser.add_argument('--scaleA',       type=int, default=10000, help='weights scaling value')
  parser.add_argument('--scaleB',       type=int, default=30, help='activation scaling value ')
  parser.add_argument('--img_raw_scale',type=float, default=255.0, help='image raw scale value ')
  parser.add_argument('--img_mean',     type=int, nargs=3, default=[104.007,116.669,122.679],  # BGR for Caffe
                      help='image mean values ')
  parser.add_argument('--img_input_scale', type=float, default=1.0, help='image input scale value ')
  parser.add_argument('--zmqpub',       action='store_true', default=False, help='publish predictions to zmq port 5555')
  parser.add_argument('--perpetual',    action='store_true', default=False, help='loop over input images forever')
  parser.add_argument('--PE',           type=int, nargs='?', default=-1, help='preferred PE to run the classification on. Default is auto-select')
  parser.add_argument('--endLayerName', type=str, default='', help='layer name till the network should be run, helpful for debugging')
  parser.add_argument('--diffStartLayer',  type=int, default=0, help="if 1 then we can run from any given layer ignoring the X's of first layers")
  parser.add_argument('--v2WeightsFormat', action='store_true', default=False, help="Weights File specified as KernSizex KernSizey instead of only KernSize, supporting rectangle kernels")
  parser.add_argument('--layerName',    type=str, default='', help='layername until which pyfpga should run, if left default, would run the entire model')
  parser.add_argument('--binaryFormatWeights', action='store_true', default=False, help="Binary Format Weights Files")

  return parser


def make_dict_args(args):
    def find_all_images(input_dict):
        if 'images' in input_dict and input_dict['images'] is not None:
            inputFiles = []
            for dir_or_image in literal_eval(str(input_dict['images'])):
                if os.path.isdir(dir_or_image):
                    inputFiles += [os.path.join(dir_or_image, f) for f in os.listdir(dir_or_image) if os.path.isfile(os.path.join(dir_or_image, f))]
                else:
                    inputFiles += [dir_or_image]
            input_dict['images'] = inputFiles

    def eval_string(input_dict):
        for key, val in list(input_dict.items()):
            try:
                input_dict[key] = literal_eval(str(val))
            except:
                pass
            #if val and str(val).isdigit():
            #    input_dict[key] = int(val)

    def ingest_xclbin_json_config(input_dict):
      fname = input_dict['xclbin'] + ".json"
      with open(fname) as data:
        xclbinJson = json.load(data)
        input_dict['overlaycfg'] = xclbinJson

        isV3 = False
        if 'XDNN_VERSION_MAJOR' in xclbinJson \
          and xclbinJson['XDNN_VERSION_MAJOR'] == "3":
          isV3 = True

        if isV3:
          input_dict['xdnnv3'] = True
          libPath = os.environ['LIBXDNN_PATH'] + ".v3"
          if os.path.isfile(libPath):
            os.environ['LIBXDNN_PATH'] = libPath

        if 'XDNN_CSR_BASE' in xclbinJson and input_dict['batch_sz'] == -1:
          csrAddrs = xclbinJson['XDNN_CSR_BASE'].split(",")
          input_dict['batch_sz'] = len(csrAddrs)
          if not isV3:
            input_dict['batch_sz'] *= 2
	
    try:
      args_dict = vars(args)
    except:
      args_dict = args
    find_all_images(args_dict)
    eval_string(args_dict)
    ingest_xclbin_json_config(args_dict)

    jsoncfg_exists = args_dict.get('jsoncfg')
    if jsoncfg_exists:
        with open(args_dict['jsoncfg']) as jsoncfgFile:
            jsoncfgs = json.load(jsoncfgFile)['confs']
            for jsoncfg in jsoncfgs:
                find_all_images(jsoncfg)
                eval_string(jsoncfg)

                # include all args not in args_dict['jsoncfg'] from original args_dict
                for key, value in list(args_dict.items()):
                    if key not in jsoncfg:
                        jsoncfg[key] = value
            args_dict['jsoncfg'] = jsoncfgs

    return args_dict

def processCommandLine(argv=None, base='TF'):
    """
    Invoke command line parser for command line deployment flows.
    """
    #parser = default_xdnn_arg_parser(base=base)
    parser = default_parser_args()
    args = parser.parse_args(argv)
    return make_dict_args(args)


# Generic list of image manipulation functions for simplifying preprocess code
def loadImageBlobFromFileScriptBase(imgFile, cmdSeq):
    if isinstance(imgFile, str):
        img = _imread(imgFile)
    else:
        img = imgFile

    orig_shape = img.shape

    for (cmd,param) in cmdSeq:
        #print "command:",cmd,"param:",param
        #print "imshape:",img.shape
        if cmd == 'resize':
            img = cv2.resize(img, (param[0], param[1]))
        elif cmd == 'resize2mindim':
            height, width, __ = img.shape
            newdim = min(height, width)
            scalew = float(width)  / newdim
            scaleh = float(height) / newdim
            mindim = min(param[0], param[1])
            neww   = int(mindim * scalew)
            newh   = int(mindim * scaleh)
            img    = cv2.resize(img, (neww, newh))
        elif cmd == 'resize2maxdim':
            # Currently doesn't work for rectangular output dimensions...
            height, width, __ = img.shape
            newdim = max(height, width)
            scalew = float(width)  / newdim
            scaleh = float(height) / newdim
            maxdim = max(param)
            neww   = int(maxdim * scalew)
            newh   = int(maxdim * scaleh)
            img    = cv2.resize(img, (neww, newh))
        elif cmd == 'crop_letterbox':
            height, width, channels = img.shape
            newdim = max(height, width)
            letter_image = np.zeros((newdim, newdim, channels))
            letter_image[:, :, :] = param
            if newdim == width:
                letter_image[(newdim-height)/2:((newdim-height)/2+height),0:width] = img
            else:
                letter_image[0:height,(newdim-width)/2:((newdim-width)/2+width)] = img
            img = letter_image
        elif cmd == 'crop_center':
            size_x = img.shape[0]
            size_y = img.shape[1]
            ll_x   = size_x//2 - param[0]//2
            ll_y   = size_y//2 - param[1]//2
            img    = img[ll_x:ll_x+param[0],ll_y:ll_y+param[1]]
        elif cmd == 'plot':
            toshow = img.astype(np.uint8)
            if param is not None:
                toshow = np.transpose(toshow, (param[0], param[1], param[2]))
            plt.imshow(toshow, cmap = 'gray', interpolation = 'bicubic')
            plt.xticks([]), plt.yticks([])  # to hide tick values on X and Y axis
            plt.show()
        elif cmd == 'pxlscale':
            if img.dtype != np.float32:
                img = img.astype(np.float32, order='C')
            if param != 1.0:
                img = img * param
        elif cmd == 'meansub':
            if img.dtype != np.float32:
                img = img.astype(np.float32, order='C')
            if isinstance(param, np.ndarray):
                img -= param
            else:
                img -= np.array(param, dtype = np.float32, order='C')
        elif cmd == 'chtranspose':
            # HWC->CWH = 2,0,1
            # CWH->HWC = 1,2,0
            img = np.transpose(img, (param[0], param[1], param[2]))
        elif cmd == 'chswap':
            # BGR->RGB = 2,1,0
            # RGB->BGR = 2,1,0
            ch = 3*[None]
            if img.shape[0] == 3:
                ch[0] = img[0,:,:]
                ch[1] = img[1,:,:]
                ch[2] = img[2,:,:]
                img   = np.stack((ch[param[0]],ch[param[1]],ch[param[2]]), axis=0)
            else:
                ch[0] = img[:,:,0]
                ch[1] = img[:,:,1]
                ch[2] = img[:,:,2]
                img   = np.stack((ch[param[0]],ch[param[1]],ch[param[2]]), axis=2)
        else:
            raise NotImplementedError(cmd)

    #    print "final imshape:",img.shape
    return img, orig_shape


# This runs image manipulation script
def loadImageBlobFromFile(imgFile, raw_scale, mean, input_scale, img_h, img_w):
    # Direct resize only
    cmdseqResize = [
        ('resize',(img_w,img_h)),
        ('pxlscale',float(raw_scale)/255),
        ('meansub', mean),
        ('pxlscale', input_scale),
        ('chtranspose',(2,0,1))
        ]
    img, orig_shape = loadImageBlobFromFileScriptBase(imgFile, cmdseqResize)

    # Change initial resize to match network training (shown as {alpha x 256 or 256 x alpha}->224,224,
    # alpha being at least 256 such that the original aspect ratio is maintained)
    #cmdseqCenterCrop = [
    #    ('resize2mindim',(256,256)),
    #    ('crop_center',(img_h,img_w)),
    #    ('pxlscale',float(raw_scale)/255),
    #    ('meansub', mean),
    #    ('pxlscale', input_scale),
    #    ('chtranspose',(2,0,1))
    #    ]
    #img, orig_shape = loadImageBlobFromFileScriptBase(imgFile, cmdseqCenterCrop)

    img = img[ np.newaxis, ...]
    np.ascontiguousarray(img, dtype=np.float32)


    return img, None


def loadYoloImageBlobFromFile(imgFile, img_h, img_w):
    # This first loads the image
    # letterboxes/resizes
    # divides by 255 to create values from 0.0 to 1.0
    # Letter boxing
    # When given a rectangular image
    # If the network expects a square input
    # Reshape the image such that its longer dimension fits exactly in the square
    # i.e.
    #    ----------
    #    |--------|
    #    | IMAGE  |
    #    |--------|
    #    ----------

    cmdseqYolov2 = [
        ('resize2maxdim',(img_w,img_h)),
        ('pxlscale',(1.0/255.0)),
        ('crop_letterbox',(0.5)),
        ('chtranspose',(2,0,1)),
        ('chswap',(2,1,0))
        ]

    img, orig_shape = loadImageBlobFromFileScriptBase(imgFile, cmdseqYolov2)
    img = img[ np.newaxis, ...]
    np.ascontiguousarray(img, dtype=np.float32)
    return img, orig_shape


def getFilePaths(paths_list):
    ext = (".jpg",".jpeg",".JPG",".JPEG")
    img_paths = []
    for p in paths_list:
        if os.path.isfile(p) and p.endswith(ext):
            img_paths.append( os.path.abspath(p) )
        else:
            for dirpath,_,filenames in os.walk(p):
                for f in filenames:
                    if f.endswith(ext):
                        img_paths.append( os.path.abspath(os.path.join(dirpath, f)))

    return img_paths


def getTopK(output, labels, topK):
    output = output.flatten()
    topKIdx = np.argsort(output)[-topK:]
    topKVals = [output[ti] for ti in topKIdx]
    topKList = zip( topKVals, topKIdx )
    topKList.reverse()
    return [(topKList[j][0], labels[topKList[j][1]]) for j in range(topK)]

def getGoldenMap(goldenFile):
    goldenMap = OrderedDict()
    with open(goldenFile, 'r') as f:
        for line in f:
            fname = line[:line.rfind(' ')]
            goldenIdx = int(line[line.rfind(' ')+1:])
            goldenMap[fname] = goldenIdx

    return goldenMap

def isTopK ( out, goldenMap, fileName, labels, topK = 5):
    f = ntpath.basename(fileName)
    topKs = getTopK(out, labels, topK)
    for (_, label) in topKs:
        if ( label == labels[goldenMap[f]]):
            return True

    return False

def get_labels (label_file):
  labels = None
  if (label_file):
    with open(label_file, 'r') as f:
      labels = [line.strip() for line in f]

  return labels

def printClassification(output, img_paths, labels, topK = 5):
  if labels is not None:
    print ( getClassification ( output, img_paths, labels, topK))

def getClassification(output, img_paths, labels, topK = 5, zmqPub = False):
  """
  Print the result of classification given class scores, and a synset labels file.

  :param output: Class scores, typically the output of the softmax layer.
  :type output: numpy.ndarray.
  :param img_paths: list of path(s) to image(s)
  :param label_file: path to label file
  :type args: dict.
  """
  ret = ""
  if not isinstance(img_paths, list):
    img_paths = [img_paths]

  for i,p in enumerate(img_paths):
    topXs = getTopK(output[i,...], labels, topK)
    inputImage = "for {:s} ".format(p if isinstance(p, str) else 'raw_input')
    if zmqPub :
      ret += (img_paths[i] + '\n')
    else :
      ret += "---------- Prediction {:d}/{:d} {:s}----------\n".format(i+1, output.shape[0], inputImage)
    for (prob, label) in topXs:
      ret += ("{:.4f} \"{:s}\"\n".format(prob, label))

  return ret


def getNearFileMatchWithPrefix(path, prefix, index = 0):
    nearMatches = [f for f in os.listdir(path) if f.startswith(prefix)]
    nearMatches.sort()
    if len(nearMatches) > 0:
        return "%s/%s" % (path, nearMatches[index])

    return None


def loadFCWeightsBias(arg, index = 0):
  data_dir = arg['weights']
  if ".h5" in data_dir:
    with h5py.File(data_dir,'r') as f:
      #keys = f.keys()
      #print (keys)
      key = list(f.keys())[0]
      weight = list(np.array(f.get(key)).flatten())
      key = list(f.keys())[1]
      bias = list(np.array(f.get(key)).flatten())
  else:
    fname = "%s/fc" % data_dir
    if not os.path.exists(fname):
      nearMatch = getNearFileMatchWithPrefix(data_dir, "fc", index)
      if nearMatch:
        fname = nearMatch
    if os.path.exists(fname):

      with open(fname, 'r') as f:
        line = f.read()
        vals = line.strip().split(' ')
        weight = [float(v) for v in vals]
    else:
      print("No FC layers found in {:s}".format(data_dir))
      return (None, None)

    fname = "%s/fc_bias" % data_dir
    if not os.path.exists(fname):
      nearMatch = getNearFileMatchWithPrefix(data_dir, "fc_bias", index)
      if nearMatch:
        fname = nearMatch
    with open(fname, 'r') as f:
      line = f.read()
      vals = line.strip().split(' ')
      bias = [float(v) for v in vals]


  return (np.asarray(weight, dtype=np.float32), np.asarray(bias, dtype=np.float32))

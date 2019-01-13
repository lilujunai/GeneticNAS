import time
import torch.nn as nn
from models import model_cnn
import gnas
import torch
import torchvision
import torchvision.transforms as transforms
import torch.optim as optim

import os
import pickle
import datetime
from config import default_config, save_config, load_config
import argparse
from cnn_utils import CosineAnnealingLR, Cutout
from common import evaulte_single, evaulte_individual_list

parser = argparse.ArgumentParser(description='PyTorch GNAS')
parser.add_argument('--config_file', type=str, help='location of the config file')
parser.add_argument('--search_dir', type=str, help='the log dir of the search')
parser.add_argument('--final', type=bool, help='location of the config file', default=False)
args = parser.parse_args()

#######################################
# Parameters
#######################################
config = default_config()
if args.config_file is not None:
    print("Loading config file:" + args.config_file)
    config.update(load_config(args.config_file))
print(config)
#######################################
# Search Working Device
#######################################
working_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(working_device)
######################################
# Read dataset and set augmentation
######################################

train_transform = transforms.Compose([])
normalize = transforms.Normalize(mean=[x / 255.0 for x in [125.3, 123.0, 113.9]],
                                 std=[x / 255.0 for x in [63.0, 62.1, 66.7]])
train_transform.transforms.append(transforms.RandomCrop(32, padding=4))
train_transform.transforms.append(transforms.RandomHorizontalFlip())
train_transform.transforms.append(transforms.ToTensor())
train_transform.transforms.append(normalize)
if config.get('cutout'):
    train_transform.transforms.append(Cutout(n_holes=config.get('n_holes'), length=config.get('length')))

transform = transforms.Compose([
    transforms.ToTensor(),
    normalize])

trainset = torchvision.datasets.CIFAR10(root='./dataset', train=True,
                                        download=True, transform=train_transform)
trainloader = torch.utils.data.DataLoader(trainset, batch_size=config.get('batch_size'),
                                          shuffle=True, num_workers=4)

testset = torchvision.datasets.CIFAR10(root='./dataset', train=False,
                                       download=True, transform=transform)
testloader = torch.utils.data.DataLoader(testset, batch_size=config.get('batch_size_val'),
                                         shuffle=False, num_workers=4)
######################################
# Config model and search space
######################################
n_cell_type = gnas.SearchSpaceType(config.get('n_block_type') - 1)
dp_control = gnas.DropPathControl(config.get('drop_path_keep_prob'))
ss = gnas.get_enas_cnn_search_space(config.get('n_nodes'), dp_control, n_cell_type)
ga = gnas.genetic_algorithm_searcher(ss, generation_size=config.get('generation_size'),
                                     population_size=config.get('population_size'), delay=config.get('delay'),
                                     keep_size=config.get('keep_size'), mutation_p=config.get('mutation_p'),
                                     min_objective=False)
net = model_cnn.Net(config.get('n_blocks'), config.get('n_channels'), config.get('num_class'), config.get('dropout'),
                    ss)
net.to(working_device)
######################################
# Build Optimizer and Loss function
#####################################
criterion = nn.CrossEntropyLoss()
optimizer = optim.SGD(net.parameters(), lr=config.get('learning_rate'), momentum=config.get('momentum'), nesterov=True,
                      weight_decay=config.get('weight_decay'))
######################################
# Select Learning schedule
#####################################
if config.get('LRType') == 'CosineAnnealingLR':
    scheduler = CosineAnnealingLR(optimizer, 10, 2, config.get('lr_min'))
else:
    scheduler = optim.lr_scheduler.MultiStepLR(optimizer,
                                               [int(config.get('n_epochs') / 2), int(3 * config.get('n_epochs') / 4)])
#
##################################################
# Generate log dir and Save Params
##################################################
log_dir = os.path.join('.', 'logs', datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
os.makedirs(log_dir, exist_ok=True)
save_config(log_dir, config)

#######################################
# Load Indvidual
#######################################
if args.final:
    ind_file = os.path.join(args.search_dir, 'best_individual.pickle')
    ind = pickle.load(open(ind_file, "rb"))
    net.set_individual(ind)
##################################################
# Start Epochs
##################################################
ra = gnas.ResultAppender()
best = 0

for epoch in range(config.get('n_epochs')):  # loop over the dataset multiple times
    # print(epoch)
    running_loss = 0.0
    correct = 0
    total = 0
    scheduler.step()
    s = time.time()
    net = net.train()
    if epoch == config.get('drop_path_start_epoch'):
        dp_control.enable()
    for i, (inputs, labels) in enumerate(trainloader, 0):
        # get the inputs
        if not args.final: net.set_individual(ga.sample_child())

        inputs = inputs.to(working_device)
        labels = labels.to(working_device)

        optimizer.zero_grad()  # zero the parameter gradients
        outputs = net(inputs)  # forward

        _, predicted = torch.max(outputs, 1)
        total += labels.size(0)
        correct += (predicted == labels).sum().item()

        loss = criterion(outputs, labels)

        loss.backward()  # backward

        optimizer.step()  # optimize

        # print statistics
        running_loss += loss.item()

    if args.final:
        f_max = evaulte_single(ind, net, testloader, working_device)
        n_diff = 0
    else:
        if config.get('full_dataset'):
            for ind in ga.get_current_generation():
                acc = evaulte_single(ind, net, testloader, working_device)
                ga.update_current_individual_fitness(ind, acc)
            _, _, f_max, _, n_diff = ga.update_population()
            best_individual = ga.best_individual
        else:
            f_max = 0
            n_diff = 0
            for _ in range(config.get('generation_per_epoch')):
                evaulte_individual_list(ga.get_current_generation(), ga, net, testloader, working_device)
                _, _, v_max, _, n_d = ga.update_population()
                n_diff += n_d
                if v_max > f_max:
                    f_max = v_max
                    best_individual = ga.best_individual
            f_max = evaulte_single(best_individual, net, testloader, working_device)  # evalute best
    if f_max > best:
        print("Update Best")
        best = f_max
        torch.save(net.state_dict(), os.path.join(log_dir, 'best_model.pt'))
        if not args.final:
            gnas.draw_network(ss, ga.best_individual, os.path.join(log_dir, 'best_graph_' + str(epoch) + '_'))
            pickle.dump(ga.best_individual, open(os.path.join(log_dir, 'best_individual.pickle'), "wb"))
    print(
        '|Epoch: {:2d}|Time: {:2.3f}|Loss:{:2.3f}|Accuracy: {:2.3f}%|Validation Accuracy: {:2.3f}%|LR: {:2.3f}|N Change : {:2d}|'.format(
            epoch, (
                           time.time() - s) / 60,
                   running_loss / i,
                   100 * correct / total, f_max,
            scheduler.get_lr()[
                -1],
            n_diff))
    ra.add_epoch_result('N', n_diff)
    ra.add_epoch_result('Best', best)
    ra.add_epoch_result('Validation Accuracy', f_max)
    ra.add_epoch_result('LR', scheduler.get_lr()[-1])
    ra.add_epoch_result('Training Loss', running_loss / i)
    ra.add_epoch_result('Training Accuracy', 100 * correct / total)
    if not args.final:
        ra.add_result('Fitness', ga.ga_result.fitness_list)
        ra.add_result('Fitness-Population', ga.ga_result.fitness_full_list)
    ra.save_result(log_dir)

print('Finished Training')

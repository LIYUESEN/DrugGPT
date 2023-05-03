# -*- coding: utf-8 -*-
"""
Created on Mon May  1 19:41:07 2023

@author: Sen
"""

import os
import sys
import subprocess
import warnings
from tqdm import tqdm
import argparse
import torch
from transformers import AutoTokenizer, GPT2LMHeadModel

warnings.filterwarnings('ignore')
#Sometimes, using Hugging Face may require a proxy.
#os.environ["http_proxy"] = "http://your.proxy.server:port"
#os.environ["https_proxy"] = "http://your.proxy.server:port"


# Set up command line argument parsing
parser = argparse.ArgumentParser()
parser.add_argument('-p', type=str, default=None, help='Input the protein amino acid sequence. Default value is None. Only one of -p and -f should be specified.')
parser.add_argument('-f', type=str, default=None, help='Input the FASTA file. Default value is None. Only one of -p and -f should be specified.')
parser.add_argument('-l', type=str, default='', help='Input the ligand prompt. Default value is an empty string.')
parser.add_argument('-n', type=int, default=100, help='Total number of generated molecules. Default value is 100.')
parser.add_argument('-d', type=str, default='cuda', help="Hardware device to use. Default value is 'cuda'.")
parser.add_argument('-o', type=str, default='./ligand_output/', help="Output directory for generated molecules. Default value is './ligand_output/'.")
parser.add_argument('-bs', type=int, default=64, help="Total number of generated molecules per batch. Try to reduce this value if you have a low RAM. Default value is 64.")

args = parser.parse_args()

protein_seq = args.p
fasta_file = args.f
ligand_prompt = args.l
max_generated_number = args.n
device = args.d
output_path = args.o
batch_size = args.bs



if not os.path.exists(output_path):
    os.makedirs(output_path)

# Function to read in FASTA file
def read_fasta_file(file_path):
    with open(file_path, 'r') as f:
        sequence = []
        
        for line in f:
            line = line.strip()
            if not line.startswith('>'):
                sequence.append(line)

        protein_sequence = ''.join(sequence)

    return protein_sequence

# Check if the input is either a protein amino acid sequence or a FASTA file, but not both
if (not protein_seq) and (not fasta_file):
    print("Error: Input is empty.")
    sys.exit(1)
if protein_seq and fasta_file:
    print("Error: The input should be either a protein amino acid sequence or a FASTA file, but not both.")
    sys.exit(1)
if fasta_file:
    protein_seq = read_fasta_file(fasta_file)

# Load the tokenizer and the model
tokenizer = AutoTokenizer.from_pretrained('liyuesen/druggpt')
model = GPT2LMHeadModel.from_pretrained("liyuesen/druggpt")

# Generate a prompt for the model
p_prompt = "<|startoftext|><P>" + protein_seq + "<L>"
l_prompt = "" + ligand_prompt 
prompt = p_prompt + l_prompt
print(prompt)

# Move the model to the specified device
model.eval()
device = torch.device(device)
model.to(device)



#Define function to filter out empty SDF files
# Define function to generate SDF files from a list of ligand SMILES using OpenBabel
def get_sdf(ligand):
    filepath = os.path.join(output_path, 'ligand_' + ligand[:100] + (ligand[100:] and "~~~") + '.sdf')
    if os.path.exists(filepath):
        return False
    cmd = "obabel -:" + ligand + " -osdf -O " + filepath + " --gen3d --forcefield mmff94"  # --conformer --nconf 1 --score rmsd
    try:
        subprocess.check_output(cmd, timeout=10)
        with open(filepath, 'r') as f:
            text = f.read()
        if len(text) < 2:
            os.remove(filepath)
            return False
        return True
    except Exception as e:
        print(e)
        return False



# Generate molecules
generated = torch.tensor(tokenizer.encode(prompt)).unsqueeze(0)
generated = generated.to(device)

generated_number = 0
batch_number = 0

while generated_number<max_generated_number:
    batch_number += 1
    print(f"Batch {batch_number}")
    sample_outputs = model.generate(
                                    generated, 
                                    #bos_token_id=random.randint(1,30000),
                                    do_sample=True,   
                                    top_k=5, 
                                    max_length = 1024,
                                    top_p=0.6, 
                                    num_return_sequences=batch_size
                                    )
    print("Converting to sdf ...")
    for sample_output in tqdm(sample_outputs):
        ligand=tokenizer.decode(sample_output, skip_special_tokens=True).split('<L>')[1]
        if get_sdf(ligand):
            generated_number += 1
        if generated_number>=max_generated_number:
            break
    print(f"{generated_number} molecules have been generated.")
    torch.cuda.empty_cache()




pdb1_name=
pdb2_name=
pdb1_path=
pdb2_path=
active1_path=
active2_path=
passive1_path=
passive2_path=


with open (pdb1_path, "r") as pdb1, open (pdb2_path, "r") as pdb2, open (active1_path, "r") as active1, open (active2_path, "r") as active2, open (passive1_path, "r") as passive1, open (passive2_path, "r") as passive2:
    linhas_pdb1 = pdb1.readlines()
    linhas_pdb2 = pdb2.readlines()
    linhas_active1 = active1.readlines()
    linhas_active2 = active2.readlines()
    linhas_passive1 = passive1.readlines()
    linhas_passive2 = passive2.readlines()

all_sites1 = [site for site in linhas_active1[0].split(",") + linhas_passive1[0].split(",") if site.strip()]
all_sites2 = [site for site in linhas_active2[0].split(",") + linhas_passive2[0].split(",") if site.strip()]


##pdb1  
list_pdb1 = []
for line in linhas_pdb1:
    if line.startswith("ATOM"):
        atoms = line.split()
        list_pdb1.append(atoms)

    new_list_pdb1 = []
    for atom in list_pdb1:
        # remover espaços em branco vazios e caracteres de nova linha
        cleaned_atom = [x.strip() for x in atom]
        new_list_pdb1.append(cleaned_atom)

##pdb2
list_pdb2 = []
for line in linhas_pdb2:
    if line.startswith("ATOM"):
        atoms = line.split()
        list_pdb2.append(atoms)

    new_list_pdb2 = []
    for atom in list_pdb2:
        cleaned_atom = [x.strip() for x in atom]
        new_list_pdb2.append(cleaned_atom)
        

restr1 = []
for nr in all_sites1:
    x = nr
    for line in new_list_pdb1:
        if int(line[5]) == int(nr):
            restr1.append(line[4] + '.' + line[3] + '.' + line[5])
restr1 = list(dict.fromkeys(restr1))

restr2 = []
for nr in all_sites2:
    x = nr
    for line in new_list_pdb2:
        if int(line[5]) == int(nr):
            restr2.append(line[4] + '.' + line[3] + '.' + line[5])
restr2 = list(dict.fromkeys(restr2))


def extract_residue_number(item):
    return int(item.split('.')[-1])

sorted_restr1 = sorted(restr1, key=extract_residue_number)
str1 = ', '.join(sorted_restr1)

a_b = ["B" + rotulo[1:] if rotulo.startswith("A.") else rotulo for rotulo in restr2]
sorted_restr2 = sorted(a_b, key=extract_residue_number)
str2 = ', '.join(sorted_restr2)




with open ("/data/$prefix"ftdock_run"/teste.ini","w") as ini:
    ini.write("[receptor]\n")
    ini.write("pdb		= {}\n".format(pdb1_name))
    ini.write("mol		= A\n")
    ini.write("newmol	= A\n")
    ini.write("restr   = {}\n".format(str1))
    ini.write("[ligand]\n")
    ini.write("pdb		= {}\n".format(pdb2_name))
    ini.write("mol		= A\n")
    ini.write("newmol	= B\n")
    ini.write("restr   = {}".format(str2))

  
  


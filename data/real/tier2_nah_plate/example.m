%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%
%   Dataset usage example
%   
%   This script load the rectangular_simulation_nah dataset
%   Plot the mesh points and the pressure and velocity example
%   
%   Author: Marco Olivieri
%   Mail:   marco1.olivieri@polimi.it
%   Data:   November 2021
%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

clear all
close all
clc

load("rectangular_simulation_nah.mat");

%% data selection

clc

use_hologram_resolution = 'Y';  % Y / N

if strcmp(use_hologram_resolution, 'Y')
    p_h_sel = p_h_downsampling;
    h_points_sel = h_points_downsampling;
else
    p_h_sel = p_h;
    h_points_sel = h_points;
end

i = randsample(length(boundary), 1);

fprintf("\n***********\nINFORMATION\n")
fprintf("selected index\t=\t%i \n", i);
fprintf("num plate\t=\t%i \n", num_plate(i));
fprintf("boundary\t=\t%s \n", boundary(i));
fprintf("mode number\t=\t%i \n", mode(i));
fprintf("frequency\t=\t%d [Hz]\n", round(freq(i), 2));

%% plot mesh points

pnt_size = 10;

figure(1)
title("Mesh Points")
scatter3(reshape(h_points_sel(i,:,:,1), [], 1), reshape(h_points_sel(i,:,:,2), [], 1), reshape(h_points_sel(i,:,:,3), [], 1), pnt_size, 'filled')
hold on
scatter3(reshape(s_points(i,:,:,1), [], 1), reshape(s_points(i,:,:,2), [], 1), reshape(s_points(i,:,:,3), [], 1), pnt_size, 'filled')
legend(["hologram points", "surface points"])

%% plot fields

figure(2)

x_h = unique(reshape(h_points_sel(i,:,:,1), [], 1));
y_h = unique(reshape(h_points_sel(i,:,:,2), [], 1));
x_s = unique(reshape(s_points(i,:,:,1), [], 1));
y_s = unique(reshape(s_points(i,:,:,2), [], 1));

subplot(221)
imagesc(x_h, y_h, abs(squeeze(p_h_sel(i, :, :))))
title("Hologram Pressure")
ylabel("Magnitude")
h = colorbar;
colorTitleHandle = get(h,'Title');
set(colorTitleHandle ,'String','Pa');

subplot(222)
imagesc(x_s, y_s, abs(squeeze(v_s(i, :, :))))
title("Normal Velocity")
h = colorbar;
colorTitleHandle = get(h,'Title');
set(colorTitleHandle ,'String','m/s');

subplot(223)
imagesc(x_h, y_h, angle(squeeze(p_h_sel(i, :, :))))
caxis([-pi pi])
ylabel("Phase")
h = colorbar;
colorTitleHandle = get(h,'Title');
set(colorTitleHandle ,'String','rad');

subplot(224)
imagesc(x_s, y_s, angle(squeeze(v_s(i, :, :))))
caxis([-pi pi])
h = colorbar;
colorTitleHandle = get(h,'Title');
set(colorTitleHandle ,'String','rad');
"""myEWB CHAMP analytics

This file is part of myEWB
Copyright 2010 Engineers Without Borders Canada

@author Francis Kung
"""

import csv, copy
from datetime import date

from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404, render_to_response
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponseNotFound, HttpResponseRedirect, HttpResponse, HttpResponseForbidden
from django.db.models import Q
from django.template import RequestContext
from django.template.loader import render_to_string

from base_groups.decorators import group_admin_required
from networks.decorators import chapter_president_required, chapter_exec_required
from networks.models import Network
from champ.models import *
from champ.views import *
from siteutils import schoolyear
from siteutils.helpers import fix_encoding, copy_model_instance
from siteutils.http import JsonResponse

def default(request):
    if not request.GET.get('stage', None):
        return select_graph(request)
    elif request.GET['stage'] == 'options' or request.GET['stage'] == 'draw':
        stage = request.GET['stage']
        graphtype = request.GET.get('graphtype', None)

        if graphtype == 'Progress to goal':
            if stage == 'options':
                return progress_options(request)
            elif stage == 'draw':
                return progress_draw(request)
                
        
        
    return HttpResponse("Internal error - lost stage")
        
def select_graph(request):
    metric = request.GET.get('metric', '')
    group = request.GET.get('group', '')
    
    return render_to_response('champ/champalytics/select.html',
                              {'metric': metric,
                               'group': group},
                              context_instance=RequestContext(request))
                              
def build_stats(group_slug=None):
    activity_filters, metric_filters = build_filters(date.today().year)
    
    if group_slug:
        grp = get_object_or_404(Network, slug=group_slug)
        
        if grp.is_chapter():
            metric_filters.append({'activity__group__slug': group_slug})

    metric_filters.append({'activity__visible': True})
    metric_filters.append({'activity__confirmed': True})
    context = run_stats(metric_filters)

    natl_activity_filters, natl_metric_filters = build_filters(date.today().year)
    natl_metric_filters.append({'activity__visible': True})
    natl_metric_filters.append({'activity__confirmed': True})
    natl_context = run_stats(natl_metric_filters)

    return context, natl_context
    
def build_stats_for(group_slug=None, metric=None):
    activity_filters, metric_filters = build_filters(date.today().year)
    
    if group_slug:
        grp = get_object_or_404(Network, slug=group_slug)
        
        if grp.is_chapter():
            metric_filters.append({'activity__group__slug': group_slug})

    metric_filters.append({'activity__visible': True})
    metric_filters.append({'activity__confirmed': True})
    context = run_stats_for(metric_filters, metric)

    natl_activity_filters, natl_metric_filters = build_filters(date.today().year)
    natl_metric_filters.append({'activity__visible': True})
    natl_metric_filters.append({'activity__confirmed': True})
    natl_context = run_stats_for(natl_metric_filters, metric)

    return context, natl_context


def progress_options(request):
    metric = request.GET.get('metric', '')
    group = request.GET.get('group', '')
    
    return render_to_response('champ/champalytics/progress_options.html',
                              {'metric': metric,
                               'group': group},
                              context_instance=RequestContext(request))
                              
def progress_draw(request):
    metric = request.GET.get('metric', '')
    group = request.GET.get('group', '')
    progressby = request.GET.get('progressby', '')
    context = {}

    natl_goals = aggregates.CHAMP_AGGREGATES
    champsays = []
    
    if progressby == 'formetric' and metric:
        allgroups = Network.objects.filter(chapter_info__isnull=False, is_active=True).order_by('name')

        progress = {}
        stats, natlstats = build_stats_for(metric=metric)
        name, ngoal = natl_goals[metric]
        useabsolute = request.GET.get('useabsolute', None)
        
        if useabsolute:
            progress['national'] = (stats, stats, ngoal)
        else:
            if ngoal:
                progress['national'] = (stats * 100 / ngoal, stats, ngoal)
            else:
                progress['national'] = (100, stats, ngoal)
        
        for g in allgroups:
            yp = YearPlan.objects.filter(group=g, year=date.today().year)
            if yp.count():
                yearplan = yp[0]
            else:
                yearplan = None
                
            if yearplan or useabsolute:
                stats, nstats = build_stats_for(g.slug, metric)

                if yearplan:                
                    yearplan_name = aggregates.YEARPLAN_MAP[metric]
                    goal = getattr(yearplan, yearplan_name)
                else:
                    goal = 0
                
                if useabsolute or goal:
                    if useabsolute:
                        progress[g.slug] = (stats, stats, goal)
                    else:
                        progress[g.slug] = (stats * 100 / goal, stats, goal)
                    
                        if g.slug == group:
                            myprogress,temp1,temp2 = progress[g.slug]
                            natlprogress,temp1,temp2 = progress['national']
                            if myprogress == 0:
                                champsays.append("Looks like you haven't done much yet; need a hand?");
                            elif myprogress - natlprogress > 20:
                                champsays.append("Way to go, you're well above national average!");
                            elif myprogress - natlprogress > 0:
                                champsays.append("You're above average here, keep it up!");
                            elif myprogress - natlprogress == 0:
                                champsays.append("You're right on national average.  What are the odds...");
                            elif myprogress - natlprogress > -20:
                                champsays.append("You're just under national average... a bit of work and you'll be on top!");
                            elif myprogress - natlprogress < -20:
                                champsays.append("Looks like this is an area for improvement; need a hand?");
                            
            # can be used to test the graph with more lines...
            #else:
            #    progress[g.slug] = 35
            
        context['progress'] = progress
        context['group'] = group
        context['metric'] = metric
        context['champsays'] = champsays
        context['useabsolute'] = useabsolute
        template = 'progress_metric'
        
    
    elif progressby == 'forchapter' and group:
        yp = YearPlan.objects.filter(group__slug=group, year=date.today().year)
        if yp.count():
            yearplan = yp[0]
            stats, national = build_stats(group)
            
            chapter_progress = {}
            national_progress = {}

            for s in stats:
                yearplan_name = aggregates.YEARPLAN_MAP[s]
                goal = getattr(yearplan, yearplan_name)
                
                name, ngoal = natl_goals[s]
                if ngoal:
                    nprogress = national[s] * 100 / ngoal
                else:
                    nprogress = 0
                
                if goal:
                    progress = stats[s] * 100 / goal
                    
                    if progress >= 100:
                        champsays.append("You've hit your goal for %s, you champion!" % s);
                    elif progress < 100 and progress > 80:
                        champsays.append("You've almost hit your %s goal - way to go!" % s);
                    elif progress < 30 and progress > 10:
                        champsays.append("Your %s numbers are a bit low... need some help?" % s);
                    elif progress < 10:
                        champsays.append("Woah, watch out for %s - better get moving..." % s);
                    
                else:
                    progress = -1
                    
                chapter_progress[s] = (progress, stats[s], goal, nprogress, national[s], ngoal)
            
            context['chapter_progress'] = chapter_progress
            
            if request.GET.get('includenatl', None):
                context['includenatl'] = True
            
        else:
            context['noyearplan'] = True
    
        context['champsays'] = champsays
        template = 'progress_chapter'
                
    else:
        return HttpResponse('oops')
    
    return render_to_response('champ/champalytics/' + template + '.html',
                              context,
                              context_instance=RequestContext(request))
                              

def draw_graph(request):
    return HttpResponse("graph")

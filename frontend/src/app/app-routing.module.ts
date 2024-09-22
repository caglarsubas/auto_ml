import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DataCollectionComponent } from './data-collection/data-collection.component';
import { PreprocessingComponent } from './preprocessing/preprocessing.component';
import { ModelingComponent } from './modeling/modeling.component';
import { EvaluationComponent } from './evaluation/evaluation.component';
import { DeploymentComponent } from './deployment/deployment.component';
import { ModelDevelopmentComponent } from './model-development/model-development.component';

const routes: Routes = [
  { path: '', redirectTo: '/model-development', pathMatch: 'full' },
  {
    path: 'model-development',
    component: ModelDevelopmentComponent,
    children: [
      { path: 'declaration', component: DataCollectionComponent },
      { path: 'preprocessing', component: PreprocessingComponent },
      { path: 'modeling', component: ModelingComponent },
      { path: 'evaluation', component: EvaluationComponent },
      { path: 'deployment', component: DeploymentComponent },
      { path: '', redirectTo: 'declaration', pathMatch: 'full' }
    ]
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }